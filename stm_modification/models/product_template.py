from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.fields import Char

class ProductTemplate(models.Model):
    _inherit = "product.template"

    project_location: Char = fields.Char(string="Project / Location")
    project_type = fields.Char(string="Type")
    building_no = fields.Char(string="Building No.")
    unit_no = fields.Char(string="Unit No.")
    unit_area = fields.Char(string="Unit Area")
    total_building_area = fields.Float(string="Total Building Area")
    cash_meter_price = fields.Monetary(string="Meter Price (Cash)", currency_field='currency_id')
    total_cash_price = fields.Monetary(string="Total Cash Price", currency_field='currency_id')
    installment_meter_price = fields.Float(string="Meter Price (Installment)")
    total_installment_price = fields.Float(string="Total Installment Price")
    unit_description = fields.Text(string="Unit Description")
    unit_location = fields.Char(string="Unit Location")
    garage_yes_no = fields.Boolean(string="Garage")
    club_house = fields.Boolean(string="Club House")
    garden_yes_no = fields.Boolean(string="Garden")
    roof_yes_no = fields.Boolean(string="Roof")
    garden_area = fields.Float(string="Garden Area")
    roof_area = fields.Float(string="Roof Area")




