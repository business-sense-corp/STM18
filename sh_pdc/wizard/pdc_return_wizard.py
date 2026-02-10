# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import api, fields, models
from odoo.exceptions import UserError


class PDCReturnWizard(models.TransientModel):
    _name = 'pdc.return.wizard'
    _description = 'PDC Return Action Wizard'

    pdc_id = fields.Many2one('pdc.wizard', string='PDC', required=True, readonly=True)
    action_type = fields.Selection([
        ('reject', 'Reject'),
        ('replace', 'Replace')
    ], string='Action Type', required=True, default='reject')
    
    # For Reject - activated when reject is selected
    reject_reason = fields.Text(string='Reason')
    
    def action_save(self):
        """Process the return action based on selection"""
        self.ensure_one()
        
        if self.action_type == 'reject':
            return self._process_reject()
        elif self.action_type == 'replace':
            return self._process_replace()
    
    def _process_reject(self):
        """Handle reject: Go to Returned state with reason, invoice stays unpaid"""
        # Validate reason is provided
        if not self.reject_reason or not self.reject_reason.strip():
            raise UserError("Please provide a rejection reason!")
        
        # Save old reference to prevent future duplication
        old_reference = self.pdc_id.reference
        
        # Update PDC to Returned state with reason
        self.pdc_id.write({
            'state': 'returned',
            'return_reason': self.reject_reason,
            'return_action': 'reject',
            'old_reference': old_reference  # Save to prevent duplication
        })
        
        # Post to chatter
        self.pdc_id.message_post(
            body=f"<b>Check Rejected</b><br/>Reason: {self.reject_reason}<br/>Reference: {old_reference}",
            subject="Check Rejected"
        )
        
        return {'type': 'ir.actions.act_window_close'}
    
    def _process_replace(self):
        """Handle replace: Go to Draft state, save old reference"""
        # Save old reference to prevent future duplication
        old_reference = self.pdc_id.reference
        
        # Update PDC to Draft state, keep old reference saved
        self.pdc_id.write({
            'state': 'draft',
            'old_reference': old_reference,  # Save to prevent duplication
            'reference': False,  # Clear reference so user must enter new one
            'return_action': 'replace',
            'return_reason': False  # Clear rejection reason if any
        })
        
        # Post to chatter
        self.pdc_id.message_post(
            body=f"<b>Check Replaced</b><br/>Old Reference: {old_reference or 'N/A'}<br/>User must enter new reference",
            subject="Check Replaced"
        )
        
        return {'type': 'ir.actions.act_window_close'}
