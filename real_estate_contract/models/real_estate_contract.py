# -*- coding: utf-8 -*-
from odoo import api, fields, models


class RealEstateContract(models.Model):
    _name = 'real.estate.contract'
    _description = 'Real Estate Sale Contract'
    _order = 'id desc'
    _rec_name = 'name'

    # ------------------------------------------------------------------
    # Core / linking fields
    # ------------------------------------------------------------------
    name = fields.Char(string='Contract Number', default='New', copy=False, readonly=True)
    sale_order_id = fields.Many2one(
        'sale.order', string='Sales Order', required=True,
        ondelete='cascade', index=True)
    sale_line_id = fields.Many2one(
        'sale.order.line', string='Order Line', ondelete='cascade')
    partner_id = fields.Many2one(
        related='sale_order_id.partner_id', store=True, string='Customer')
    company_id = fields.Many2one(
        related='sale_order_id.company_id', store=True)
    currency_id = fields.Many2one(
        related='sale_order_id.currency_id', store=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancelled', 'Cancelled')],
        default='confirmed', string='Status', tracking=True)
    date_confirmed = fields.Datetime(string='Confirmation Date', default=fields.Datetime.now)

    # ------------------------------------------------------------------
    # Product reference
    # ------------------------------------------------------------------
    product_id = fields.Many2one('product.product', string='Unit')
    product_name = fields.Char(string='Unit Name')
    categ_id = fields.Many2one('product.category', string='Category')

    # ------------------------------------------------------------------
    # Fields copied as-is from product.template custom fields
    # ------------------------------------------------------------------
    project_location = fields.Char(string='Project / Location')
    project_type = fields.Char(string='Type')
    building_no = fields.Char(string='Building No.')
    unit_no = fields.Char(string='Unit No.')
    unit_area = fields.Char(string='Unit Area')
    total_building_area = fields.Float(string='Total Building Area')
    unit_location = fields.Char(string='Unit Location')
    unit_description = fields.Text(string='Unit Description')

    cash_meter_price = fields.Monetary(string='Meter Price (Cash)', currency_field='currency_id')
    total_cash_price = fields.Monetary(string='Total Cash Price', currency_field='currency_id')
    installment_meter_price = fields.Float(string='Meter Price (Installment)')
    total_installment_price = fields.Float(string='Total Installment Price')

    garage_yes_no = fields.Boolean(string='Garage')
    club_house = fields.Boolean(string='Club House')
    garden_yes_no = fields.Boolean(string='Garden')
    roof_yes_no = fields.Boolean(string='Roof')
    garden_area = fields.Float(string='Garden Area')
    roof_area = fields.Float(string='Roof Area')

    _sql_constraints = [
        ('sale_line_uniq', 'unique(sale_line_id)',
         'There is already contract related to this order'),
    ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _prepare_contract_vals(self, line):
        """Build the create() vals for a contract from a confirmed sale.order.line.
        All product fields are copied as-is (no transformation/logic)."""
        product = line.product_id
        return {
            'sale_order_id': line.order_id.id,
            'sale_line_id': line.id,
            'product_id': product.id,
            'product_name': product.name,
            'categ_id': product.categ_id.id,
            'project_location': product.project_location,
            'project_type': product.project_type,
            'building_no': product.building_no,
            'unit_no': product.unit_no,
            'unit_area': product.unit_area,
            'total_building_area': product.total_building_area,
            'unit_location': product.unit_location,
            'unit_description': product.unit_description,
            'cash_meter_price': product.cash_meter_price,
            'total_cash_price': product.total_cash_price,
            'installment_meter_price': product.installment_meter_price,
            'total_installment_price': product.total_installment_price,
            'garage_yes_no': product.garage_yes_no,
            'club_house': product.club_house,
            'garden_yes_no': product.garden_yes_no,
            'roof_yes_no': product.roof_yes_no,
            'garden_area': product.garden_area,
            'roof_area': product.roof_area,
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'real.estate.contract') or 'New'
        return super().create(vals_list)
