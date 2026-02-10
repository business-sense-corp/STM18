from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountStatementWizard(models.TransientModel):
    _name = 'account.statement.wizard'
    _description = 'Account Statement Wizard'

    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        domain=[('customer_rank', '>', 0)],
        help='Select the customer for the statement'
    )
    date_from = fields.Date(
        string='Date From',
        help='Start date for the statement. Leave empty for all transactions.'
    )
    date_to = fields.Date(
        string='Date To',
        default=fields.Date.context_today,
        required=True,
        help='End date for the statement'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        )


    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to:
                if wizard.date_from > wizard.date_to:
                    raise UserError(_('Date From must be before Date To.'))

    
    @api.onchange('product_id')
    def _onchnage_product_id_fill_partner(self):
        for item in self:
            if not item.product_id:
                item.partner_id = False
                continue

            line = self.env['account.move.line'].search([
                ('product_id', '=', item.product_id.id),
                ('move_id.move_type', '=', 'out_invoice'),
                ('parent_state', '=', 'posted'),
                ],order='date asc', limit=1)
            item.partner_id = line.move_id.partner_id if line else False




    def action_print_statement(self):

        self.ensure_one()
        
        # if not self.partner_id:
        #     raise UserError(_('Please select a customer.'))
        
        if not self.partner_id and not self.product_id:
            raise UserError('Enter Customer or Product')
        
        data = {
            'partner_id': self.partner_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company_id': self.company_id.id,
            'product_id': self.product_id.id,
        }
        
        return self.env.ref('stm_modification.action_report_account_statement').report_action(
            self, data=data
        )
