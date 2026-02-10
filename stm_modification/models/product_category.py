from odoo import models, fields


class ProductCategory(models.Model):
    _inherit = "product.category"

    location_address = fields.Char(
        string="Location Address",
        help="location address for this product category."
    )