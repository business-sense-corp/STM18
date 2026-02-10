# -*- coding: utf-8 -*-

from odoo import models, api, fields, _
from odoo.exceptions import UserError
from datetime import datetime


class AccountStatementReport(models.AbstractModel):
    _name = 'report.stm_modification.statement_report_template'
    _description = 'Account Statement Report'

    @api.model
    def _get_report_values(self, docids, data=None):

        # if not data or not data.get('partner_id'):
        #     raise UserError(_('No customer selected for the statement.'))

        partner_id = data.get('partner_id')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        product_id = data.get('product_id')

        if isinstance(date_from, str):
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        if isinstance(date_to, str):
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()

        partner = self.env['res.partner'].browse(partner_id)
        company = self.env.company

        account_lines = self._get_account_lines(partner_id, date_from, date_to)
        balance_forward = self._get_balance_forward(partner_id, date_from)
        current_balance = self._get_balance_due(partner_id, date_to)

        # ======================
        # UNIT INFORMATION
        # ======================
        unit_product = False
        unit_amount = 0.0

        invoice_line = self.env['account.move.line'].search([
            ('partner_id', '=', partner_id),
            ('move_id.move_type', '=', 'out_invoice'),
            ('parent_state', '=', 'posted'),
            ('product_id', '=', product_id),
        ], order='date asc', limit=1)

        installments = []
        if invoice_line:
            unit_product = invoice_line.product_id
            unit_amount = invoice_line.price_unit
            installments = invoice_line.move_id.pdc_payment_ids # model has last table lines data



        # ======================
        # PAYMENT / CHEQUES SUMMARY
        # ======================

        total_cheques = len(installments)
        cheques_collected = len(installments.filtered(lambda c: c.state in ['done', 'cashed'])) if len(installments) > 0 else 0
        collected_amount = sum(installments.filtered(lambda c: c.state in ['done', 'cashed']).mapped('payment_amount')) if len(installments) > 0 else 0
        cheques_rejected = len(installments.filtered(lambda c: c.state == 'cancel')) if len(installments) > 0 else 0
        cheques_remaining = total_cheques - cheques_collected

        return {
            'doc_ids': [partner.id],
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

            'unit_product': unit_product,
            'unit_amount': unit_amount,

            'collected_amount': collected_amount,
            'outstanding_amount': current_balance,

            'total_cheques': total_cheques,
            'cheques_collected': cheques_collected,
            'cheques_rejected': cheques_rejected,
            'cheques_remaining': cheques_remaining,
            'installment_lines': installments,
        }

    # =====================================================
    def _get_account_lines(self, partner_id, date_from, date_to):

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
        if not date_from:
            return 0.0

        lines = self.env['account.move.line'].search([
            ('partner_id', '=', partner_id),
            ('account_id.account_type', 'in', ['asset_receivable', 'liability_payable']),
            ('parent_state', '=', 'posted'),
            ('date', '<', date_from),
        ])

        return sum(l.debit - l.credit for l in lines)

    def _get_balance_due(self, partner_id, date_to):

        domain = [
            ('partner_id', '=', partner_id),
            ('account_id.account_type', 'in', ['asset_receivable', 'liability_payable']),
            ('parent_state', '=', 'posted'),
        ]

        if date_to:
            domain.append(('date', '<=', date_to))

        lines = self.env['account.move.line'].search(domain)
        return sum(l.debit - l.credit for l in lines)
