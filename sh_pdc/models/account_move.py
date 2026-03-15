# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import api, fields, models


class AccountInvoice(models.Model):
    _inherit = "account.move"

    is_boolean = fields.Boolean(compute="compute_is_boolean")

    def compute_is_boolean(self):
        for rec in self:
            rec.is_boolean = False
            if rec.pdc_payment_ids.filtered(lambda x: x.state in ['registered', 'deposited']):
                rec.is_boolean = True

    def open_pdc_payment(self):
        [action] = self.env.ref('sh_pdc.sh_pdc_payment_menu_action').read()
        action['domain'] = [('id', 'in', self.pdc_payment_ids.ids)]
        return action

    def _compute_pdc_payment(self):
        for rec in self:
            rec.pdc_payment_count = len(self.pdc_payment_ids)

    pdc_id = fields.Many2one('pdc.wizard')
    # pdc_payment_ids = fields.Many2many(
    #     'pdc.wizard', compute='_compute_pdc_payment_invoice')
    pdc_payment_count = fields.Integer(
        "Pdc payment count", compute='_compute_pdc_payment')
    total_pdc_payment = fields.Monetary("Total ", compute='_compute_total_pdc')
    total_pdc_pending = fields.Monetary(
        "Total Pending", compute='_compute_total_pdc')
    total_pdc_cancel = fields.Monetary(
        "Total Cancel", compute='_compute_total_pdc')
    total_pdc_received = fields.Monetary(
        "Total Received", compute='_compute_total_pdc')

    # NEW: Rejection reason field
    rejection_reason = fields.Text(
        "Rejection Reason", compute='_compute_rejection_reason', store=True, readonly=True)
    pdc_payment_ids = fields.Many2many(
        'pdc.wizard',
        compute='_compute_pdc_payment_invoice',
        search='_search_pdc_payment_ids'  # ← أضف ده
    )

    def _search_pdc_payment_ids(self, operator, value):
        pdcs = self.env['pdc.wizard'].search([('id', operator, value)])
        move_ids = pdcs.mapped('invoice_id').ids
        move_ids += self.env['account.move'].search([
            ('id', 'in', pdcs.mapped('invoice_ids').ids)
        ]).ids
        return [('id', 'in', list(set(move_ids)))]

    # UPDATED: Includes all new states (return, rejected, replaced, cashed)
    sh_pdc_status = fields.Selection([
        ('draft', 'Draft'),
        ('registered', 'Registered'),
        ('deposited', 'Deposited'),
        ('return', 'Return'),
        ('rejected', 'Rejected'),
        ('replaced', 'Replaced'),
        ('cashed', 'Cashed'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], string="PDC Status", compute='_compute_latest_pdc_payment_status', store=True,
        search='_search_latest_pdc_payment_status')

    @api.depends('pdc_payment_ids.state', 'pdc_payment_ids.return_action')
    def _compute_latest_pdc_payment_status(self):
        for rec in self:
            rec.sh_pdc_status = False
            if rec.pdc_payment_ids:
                latest_pdc = rec.pdc_payment_ids[-1]
                # Just use the state directly now
                rec.sh_pdc_status = latest_pdc.state

    @api.depends('pdc_payment_ids.return_reason', 'pdc_payment_ids.state')
    def _compute_rejection_reason(self):
        for rec in self:
            rec.rejection_reason = False
            if rec.pdc_payment_ids:
                latest_pdc = rec.pdc_payment_ids[-1]
                # Get rejection reason if state is rejected
                if latest_pdc.state == 'rejected':
                    rec.rejection_reason = latest_pdc.return_reason

    # @api.depends('pdc_payment_ids.state')
    # def _compute_payment_state(self):
    #     """Override to mark invoice as paid when PDC is done or cashed"""
    #     # First call parent to compute default payment state
    #     super(AccountInvoice, self)._compute_payment_state()
    #
    #     # Then override for PDC payments
    #     for move in self:
    #         if move.pdc_payment_ids:
    #             latest_pdc = move.pdc_payment_ids[-1]
    #
    #             if latest_pdc.state in ['deposited']:
    #                 move.payment_state = 'in_payment'
    #             # If PDC is done or cashed, mark invoice as paid
    #             if latest_pdc.state in ['done', 'cashed']:
    #                 move.payment_state = 'paid'

    @api.depends(
        'pdc_payment_ids.state',
        'pdc_payment_ids.payment_amount',
        'pdc_payment_ids.effective_invoice_amount',
        'amount_total',
        'amount_residual'
    )
    def _compute_payment_state(self):
        for move in self:
            if not move.pdc_payment_ids:
                super(AccountInvoice, move)._compute_payment_state()
                continue

            if move.pdc_payment_ids.filtered(lambda p: p.state in ('registered', 'deposited')):
                move.payment_state = 'in_payment'
                continue

            valid_pdcs = move.pdc_payment_ids.filtered(
                lambda p: p.state not in ('draft', 'replaced', 'cancel', 'rejected')
            )

            total_pdc_amount = sum(valid_pdcs.mapped('effective_invoice_amount'))
            invoice_total = move.amount_total

            if total_pdc_amount == 0:
                move.payment_state = 'not_paid'
            elif 0 < total_pdc_amount < invoice_total:
                move.payment_state = 'partial'
            else:
                move.payment_state = 'paid'

    def _search_latest_pdc_payment_status(self, operator, value):

        results = []
        moves = self.env['account.move'].search([])
        if operator == '>':
            for rec in moves:
                pdc_payment_ids = self.env['pdc.wizard'].search([('id', 'in', rec.pdc_payment_ids.ids)])
                if pdc_payment_ids:
                    results.extend(pdc_payment_ids.ids)

            return [('id', 'in', results)]
        elif operator == '=':

            pdc_payment_ids = self.env['pdc.wizard'].search([('id', 'not in', moves.mapped('pdc_payment_ids').ids)])
            if pdc_payment_ids:
                results.extend(pdc_payment_ids.ids)

            return [('id', 'in', results)]

    @api.depends(
        'pdc_payment_ids.state',
        'pdc_payment_ids.payment_amount',
        'pdc_payment_ids.effective_invoice_amount'
    )
    def _compute_total_pdc(self):
        for rec in self:
            rec.total_pdc_payment = 0.0
            rec.total_pdc_pending = 0.0
            rec.total_pdc_cancel = 0.0
            rec.total_pdc_received = 0.0

            if rec.pdc_payment_ids:
                for pdc_payment in rec.pdc_payment_ids:
                    if pdc_payment.state in ('done', 'cashed'):
                        rec.total_pdc_received += pdc_payment.effective_invoice_amount

                    elif pdc_payment.state in ('cancel', 'rejected', 'replaced'):
                        rec.total_pdc_cancel += 0.0   # أو payment_amount لو عايز تعرضهم في cancel

                    elif pdc_payment.state in ('draft', 'registered', 'deposited', 'return'):
                        rec.total_pdc_pending += pdc_payment.effective_invoice_amount

            rec.total_pdc_payment = rec.total_pdc_pending + rec.total_pdc_received

    def _compute_pdc_payment_invoice(self):
        self.pdc_payment_ids = False
        for move in self:
            pdcs = self.env["pdc.wizard"].search([
                '|', ('invoice_id', '=', move.id), ('invoice_ids.id', '=', move.id)
            ])
            if pdcs:
                move.pdc_payment_ids = [(6, 0, pdcs.ids)]

    def action_update_latest_pdc_status(self):
        for rec in self:
            rec.sh_pdc_status = False
            if rec.pdc_payment_ids:
                rec.sh_pdc_status = rec.pdc_payment_ids[-1].state
