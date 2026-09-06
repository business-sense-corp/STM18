# -*- coding: utf-8 -*-

from odoo import models, api, fields
from datetime import datetime
from collections import defaultdict


class AccountStatementReport(models.AbstractModel):
    _name = 'report.stm_modification.statement_report_template'
    _description = 'Account Statement Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}

        partner_id = data.get('partner_id') or False
        product_id = data.get('product_id') or False
        date_from = data.get('date_from')
        date_to = data.get('date_to')

        if isinstance(date_from, str):
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        if isinstance(date_to, str):
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()

        company = self.env.company
        partner = self.env['res.partner'].browse(partner_id) if partner_id else self.env['res.partner']

        account_lines = self._get_account_lines(partner_id, date_from, date_to) if partner_id else []
        balance_forward = self._get_balance_forward(partner_id, date_from) if partner_id else 0.0
        current_balance = self._get_balance_due(partner_id, date_to) if partner_id else 0.0

        # ======================
        # UNITS + INSTALLMENTS
        # ======================
        units = []
        all_installments = self.env['pdc.wizard']
        all_invoices = self.env['account.move']

        line_domain = [
            ('move_id.move_type', '=', 'out_invoice'),
            ('parent_state', '=', 'posted'),
        ]

        if partner_id:
            line_domain.append(('partner_id', '=', partner_id))

        if date_from:
            line_domain.append(('date', '>=', date_from))
        if date_to:
            line_domain.append(('date', '<=', date_to))

        if product_id:
            # هات أوامر البيع اللي فيها المنتج ده، عشان نلاقي سطور الـ down payment التابعة لنفس الأوردر
            related_orders = self.env['sale.order.line'].search([
                ('product_id', '=', product_id),
            ]).mapped('order_id')

            # هات سطور الفاتورة: إما المنتج نفسه، أو سطر down payment تابع لنفس الأوردر
            line_domain += ['|',
                ('product_id', '=', product_id),
                '&',
                ('sale_line_ids.is_downpayment', '=', True),
                ('sale_line_ids.order_id', 'in', related_orders.ids),
            ]

        invoice_lines = self.env['account.move.line'].search(line_domain, order='date asc, id asc')

        if (not partner_id) and product_id and invoice_lines:
            partner = invoice_lines[0].partner_id

        grouped = defaultdict(lambda: {
            'unit_product': self.env['product.product'],
            'unit_amount': 0.0,
            'installments': self.env['pdc.wizard'],
            'cheque_summary': {},
        })

        for line in invoice_lines:
            unit = line.product_id
            sale_line = line.sale_line_ids[:1]

            # لو السطر ده down payment، دوّر على المنتج الحقيقي بتاع نفس الأوردر
            if sale_line and sale_line.is_downpayment:
                order = sale_line.order_id
                real_lines = order.order_line.filtered(lambda l: not l.is_downpayment)
                real_products = real_lines.mapped('product_id')

                if len(real_products) == 1:
                    unit = real_products[0]
                elif product_id and any(p.id == product_id for p in real_products):
                    unit = self.env['product.product'].browse(product_id)
                # لو أكتر من منتج ومفيش فلتر: سيبها تحت منتج Down Payment

            g = grouped[unit.id]

            if not g['unit_product']:
                g['unit_product'] = unit
                g['unit_amount'] = line.price_unit

            g.setdefault('invoices', self.env['account.move'])
            g['invoices'] |= line.move_id

            inst = line.move_id.pdc_payment_ids
            if inst:
                g['installments'] |= inst

        for _, g in grouped.items():
            if not g['unit_product']:
                continue

            inst = g['installments']
            total = len(inst)

            collected_rs = inst.filtered(lambda c: c.state in ['done', 'cashed'])
            rejected_rs = inst.filtered(lambda c: c.state == 'cancel')
            remaining_rs = inst - collected_rs - rejected_rs

            collected_count = len(collected_rs)
            rejected_count = len(rejected_rs)
            remaining_count = len(remaining_rs)

            collected_amount_unit = sum(collected_rs.mapped('payment_amount')) if total else 0.0
            remaining_amount_unit = sum(remaining_rs.mapped('payment_amount')) if total else 0.0
            cash_amount_unit = sum(
                self._get_cash_paid_amount(inv) for inv in g.get('invoices', self.env['account.move'])
            )
            collected_amount_unit += cash_amount_unit

            g['cheque_summary'] = {
                'total': total,
                'collected': collected_count,
                'rejected': rejected_count,
                'remaining': remaining_count,
                'collected_amount': collected_amount_unit,
                'remaining_amount': remaining_amount_unit,
                'cash_amount': cash_amount_unit,
            }

            units.append(g)
            all_installments |= inst
            all_invoices |= g.get('invoices', self.env['account.move'])

        # ======================
        # SUMMARY (overall)
        # ======================
        total_cheques = len(all_installments)
        cheques_collected = len(all_installments.filtered(lambda c: c.state in ['done', 'cashed'])) if total_cheques else 0
        collected_amount = sum(all_installments.filtered(lambda c: c.state in ['done', 'cashed']).mapped('payment_amount')) if total_cheques else 0.0
        cheques_rejected = len(all_installments.filtered(lambda c: c.state == 'cancel')) if total_cheques else 0
        cheques_remaining = total_cheques - cheques_collected

        total_cash_amount = sum(
            self._get_cash_paid_amount(inv) for inv in all_invoices
        )
        collected_amount += total_cash_amount

        return {
            'doc_ids': partner.ids if partner else [],
            'doc_model': 'res.partner',
            'docs': partner,
            'partner': partner,
            'company': company,
            'date_from': date_from,
            'date_to': date_to,
            'statement_date': date_to or fields.Date.today(),
            'account_lines': account_lines,
            'balance_forward': balance_forward,
            'current_balance': current_balance,
            'units': units,

            'collected_amount': collected_amount,
            'outstanding_amount': current_balance if partner_id else 0.0,
            'total_cheques': total_cheques,
            'cheques_collected': cheques_collected,
            'cheques_rejected': cheques_rejected,
            'cheques_remaining': cheques_remaining,
        }

    def _get_account_lines(self, partner_id, date_from, date_to):
        if not partner_id:
            return []

        domain = [
            ('partner_id', '=', partner_id),
            ('account_id.account_type', 'in', ['asset_receivable', 'liability_payable']),
            ('parent_state', '=', 'posted'),
        ]

        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))

        move_lines = self.env['account.move.line'].search(domain, order='date asc, id asc')

        lines = []
        running_balance = self._get_balance_forward(partner_id, date_from)

        for line in move_lines:
            running_balance += (line.debit - line.credit)
            lines.append({
                'date': line.date,
                'type': line.move_id.move_type,
                'description': line.name or '',
                'debit': line.debit,
                'credit': line.credit,
                'balance': running_balance,
            })

        return lines

    def _get_balance_forward(self, partner_id, date_from):
        if (not partner_id) or (not date_from):
            return 0.0

        lines = self.env['account.move.line'].search([
            ('partner_id', '=', partner_id),
            ('account_id.account_type', 'in', ['asset_receivable', 'liability_payable']),
            ('parent_state', '=', 'posted'),
            ('date', '<', date_from),
        ])
        return sum(l.debit - l.credit for l in lines)

    def _get_balance_due(self, partner_id, date_to):
        if not partner_id:
            return 0.0

        domain = [
            ('partner_id', '=', partner_id),
            ('account_id.account_type', 'in', ['asset_receivable', 'liability_payable']),
            ('parent_state', '=', 'posted'),
        ]
        if date_to:
            domain.append(('date', '<=', date_to))

        lines = self.env['account.move.line'].search(domain)
        return sum(l.debit - l.credit for l in lines)

    def _get_cash_paid_amount(self, invoice):
        """المبالغ المحصّلة عن طريق دفعات عادية (كاش/بنك) - مش عن طريق PDC"""
        if not invoice:
            return 0.0

        receivable_lines = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
        )
        if not receivable_lines:
            return 0.0

        paid = 0.0
        for line in receivable_lines:
            matched = line.matched_credit_ids | line.matched_debit_ids
            for partial in matched:
                counterpart_line = (
                    partial.debit_move_id
                    if partial.debit_move_id.id != line.id
                    else partial.credit_move_id
                )
                if counterpart_line.move_id.pdc_id:
                    continue
                if counterpart_line.payment_id or counterpart_line.statement_line_id:
                    paid += partial.amount

        return paid