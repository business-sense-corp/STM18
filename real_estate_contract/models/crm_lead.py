# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    # ------------------------------------------------------------------
    # Product reference
    # ------------------------------------------------------------------
    product_id = fields.Many2one('product.product', string='Unit')
    product_name = fields.Char(string='Unit Name')
    categ_id = fields.Many2one('product.category', string='Project')

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

    cash_meter_price = fields.Monetary(string='Meter Price (Cash)', currency_field='company_currency')
    total_cash_price = fields.Monetary(string='Total Cash Price', currency_field='company_currency')
    installment_meter_price = fields.Float(string='Meter Price (Installment)')
    total_installment_price = fields.Float(string='Total Installment Price')

    garage_yes_no = fields.Boolean(string='Garage')
    club_house = fields.Boolean(string='Club House')
    garden_yes_no = fields.Boolean(string='Garden')
    roof_yes_no = fields.Boolean(string='Roof')
    garden_area = fields.Float(string='Garden Area')
    roof_area = fields.Float(string='Roof Area')
    internal_notes = fields.Html(string='Internal Notes')

    # ------------------------------------------------------------------
    # Onchange: copy product fields as-is when product_id is set/changed
    # ------------------------------------------------------------------
    @api.onchange('product_id')
    def _onchange_product_id(self):
        for lead in self:
            if not lead.product_id:
                continue
            product = lead.product_id
            lead.update({
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
                'internal_notes': product.description,
            })