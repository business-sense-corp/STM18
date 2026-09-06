# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    contract_ids = fields.One2many(
        'real.estate.contract', 'sale_order_id', string='Contracts')
    contract_count = fields.Integer(
        string='Contract Count', compute='_compute_contract_count')

    def _compute_contract_count(self):
        for order in self:
            order.contract_count = len(order.contract_ids)

    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            order._create_real_estate_contracts()
        return res

    def _create_real_estate_contracts(self):
        """Create one real.estate.contract per eligible order line.
        Skips section/note lines, down payment lines, and lines that
        already have a contract (idempotent on re-confirmation)."""
        self.ensure_one()
        Contract = self.env['real.estate.contract']
        for line in self.order_line:
            if line.display_type:
                continue
            if line.is_downpayment:
                continue
            if not line.product_id:
                continue
            if Contract.search_count([('sale_line_id', '=', line.id)]):
                continue
            Contract.create(Contract._prepare_contract_vals(line))

    def action_view_contracts(self):
        self.ensure_one()
        action = {
            'name': 'Contracts',
            'type': 'ir.actions.act_window',
            'res_model': 'real.estate.contract',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {'default_sale_order_id': self.id},
        }
        if self.contract_count == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.contract_ids[0].id
        return action
