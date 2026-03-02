# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from datetime import timedelta, date


class Attachment(models.Model):
    _inherit = 'ir.attachment'

    pdc_id = fields.Many2one('pdc.wizard')


class PDCWizard(models.Model):
    _name = "pdc.wizard"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _description = "PDC Wizard"



    def _check_reference_ready(self):
        for rec in self:
            if not rec.reference or rec.reference.strip() == '/':
                raise UserError("Please set a valid Cheque Reference.")

    # pdc only be allowed to delete in draft state
    def unlink(self):

        for rec in self:
            if rec.state != 'draft':
                raise UserError("You can only delete draft state pdc")

        return super().unlink()



    # @api.constrains('reference')
    # def _check_reference_not_old_reference(self):
    #     for record in self:
    #         ref = (record.reference or '').strip()
    #         if not ref or ref == '/':
    #             continue
    #
    #         old_duplicate = self.search([
    #             ('old_reference', '=', ref),
    #             ('id', '!=', record.id)
    #         ], limit=1)
    #
    #         if old_duplicate:
    #             raise ValidationError(
    #                 "This cheque reference was used before (as an old reference) "
    #                 f"in PDC: {old_duplicate.name}. Please use a different number."
    #             )



    def action_register_check(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')
        account_move_model = self.env[active_model].browse(active_id)

        if account_move_model.move_type not in ('out_invoice', 'in_invoice'):
            raise UserError(
                "Only Customer invoice and vendor bills are considered!")

        move_listt = []
        payment_amount = 0.0
        payment_type = ''
        if len(active_ids) > 0:
            account_moves = self.env[active_model].browse(active_ids)
            partners = account_moves.mapped('partner_id')
            if len(set(partners)) != 1:
                raise UserError('Partners must be same')

            states = account_moves.mapped('state')
            if len(set(states)) != 1 or states[0] != 'posted':
                raise UserError(
                    'Only posted invoices/bills are considered for PDC payment!!')

            for account_move in account_moves:
                if account_move.payment_state != 'paid' and account_move.amount_residual != 0.0:
                    payment_amount = payment_amount + account_move.amount_residual
                    move_listt.append(account_move.id)
        if not move_listt:
            raise UserError("Selected invoices/bills are already paid!!")

        if account_moves[0].move_type in ('in_invoice'):
            payment_type = 'send_money'

        if account_moves[0].move_type in ('out_invoice'):
            payment_type = 'receive_money'

        return {
            'name': 'PDC Payment',
            'res_model': 'pdc.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('sh_pdc.sh_pdc_wizard_form_wizard').id,
            'context': {
                'default_invoice_ids': [(6, 0, move_listt)],
                'default_partner_id': account_move_model.partner_id.id,
                'default_payment_amount': payment_amount,
                'default_payment_type': payment_type
            },
            'target': 'new',
            'type': 'ir.actions.act_window'
        }

    def open_attachments(self):
        [action] = self.env.ref('base.action_attachment').read()

        action['domain'] = [('id', 'in', self.attachment_ids.ids)]
        return action

    def open_journal_items(self):
        self.ensure_one()
        [action] = self.env.ref('account.action_account_moves_all').read()

        # 1. البحث عن كل السطور المرتبطة بهذا الشيك
        all_lines = self.env['account.move.line'].search([('pdc_id', '=', self.id)])

        # 2. ترتيب القيود من الأحدث (ID الأكبر) إلى الأقدم
        # قيد الـ Done هو الأحدث، يليه الـ Deposit، يليه الـ Register
        all_moves = all_lines.mapped('move_id').sorted(lambda m: m.id, reverse=True)

        if not all_moves:
            action['domain'] = [('id', '=', False)]
            return action

        if not all_moves or self.state == 'return':
            action['domain'] = [('id', '=', False)]  # لا يظهر أي شيء
            return action
        # 3. الفلترة بناءً على الحالة الحالية
        if self.state in ('deposited', 'cashed', 'done'):
            # يعرض فقط سطرين "آخر عملية" تمت (سواء إيداع أو تحصيل)
            target_move = all_moves[0]
            action['domain'] = [('move_id', '=', target_move.id)]

        elif self.state == 'registered':
            # يعرض سطرين قيد التسجيل الأول
            target_move = all_moves[-1]  # الأقدم
            action['domain'] = [('move_id', '=', target_move.id)]
        elif self.state in ('rejected', 'replaced'):
            # في حالة الرفض، أنت قمت بإنشاء قيدين (عكس تسجيل وعكس إيداع)
            # سنعرض آخر قيدين تم إنشاؤهما
            target_moves = all_moves[:2]  # يأخذ أول قيدين في القائمة المرتبة تنازلياً
            action['domain'] = [('move_id', 'in', target_moves.ids)]
        else:
            # في الحالات الأخرى (مثل Draft أو Cancel) يعرض كل شيء أو لا شيء
            action['domain'] = [('id', 'in', all_lines.ids)]

        return action

    def open_journal_entry(self):
        [action] = self.env.ref(
            'sh_pdc.sh_pdc_action_move_journal_line').read()
        ids = self.env['account.move'].search([('pdc_id', '=', self.id)])
        id_list = []
        for pdc_id in ids:
            id_list.append(pdc_id.id)
        action['domain'] = [('id', 'in', id_list)]
        return action

    @api.model
    def default_get(self, fields):
        rec = super().default_get(fields)
        active_ids = self._context.get('active_ids')
        active_model = self._context.get('active_model')

        # Check for selected invoices ids
        if not active_ids or active_model != 'account.move':
            return rec
        invoices = self.env['account.move'].browse(active_ids)
        if invoices and len(invoices) == 1:
            invoice = invoices[0]
            if invoice.move_type in ('out_invoice', 'out_refund'):
                rec.update({'payment_type': 'receive_money'})
            elif invoice.move_type in ('in_invoice', 'in_refund'):
                rec.update({'payment_type': 'send_money'})

            rec.update({'partner_id': invoice.partner_id.id,
                        'payment_amount': invoice.amount_residual,
                        'invoice_id': invoice.id,
                        'due_date': invoice.invoice_date_due,
                        'memo': invoice.name})

        return rec

    name = fields.Char("Name", default='New', readonly=True, tracking=True)
    # check_amount_in_words = fields.Char(string="Amount in Words",compute='_compute_check_amount_in_words')
    payment_type = fields.Selection([('receive_money', 'Receive Money'), (
        'send_money', 'Send Money')], string="Payment Type", default='receive_money', tracking=True)
    partner_id = fields.Many2one(
        'res.partner', string="Partner", tracking=True)
    payment_amount = fields.Monetary("Payment Amount", tracking=True)
    currency_id = fields.Many2one(
        'res.currency', string="Currency", default=lambda self: self.env.company.currency_id, tracking=True)
    reference = fields.Char("Cheque Reference", required=True, tracking=True)
    # journal_id = fields.Many2one('account.journal', string="Payment Journal", domain=[
    #     ('type', '=', 'bank')], required=True, tvracking=True)
    journal_id = fields.Many2one(
        'account.journal',
        string="Payment Journal",
        domain="[('type', 'in', ('bank', 'cash'))]",
        required=True,
        tracking=True
    )
    # cheque_status = fields.Selection([('draft', 'Draft'), ('deposit', 'Deposit'), (
    #     'paid', 'Paid')], string="Cheque Status", default='draft', tracking=True)
    cheque_status = fields.Selection([('draft', 'Draft')], string="Cheque Status", default='draft', tracking=True)
    payment_date = fields.Date(
        "Payment Date", default=fields.Date.today(), required=True, tracking=True)
    due_date = fields.Date("Due Date", required=True, tracking=True)
    memo = fields.Char("Memo", required=True, tracking=True)
    agent = fields.Char("Agent", tracking=True)
    bank_id = fields.Many2one('res.bank', string="Bank", tracking=True)
    attachment_ids = fields.Many2many(
        'ir.attachment', 'pdc_attachment_rel', string='Cheque Image')
    company_id = fields.Many2one(
        'res.company', string='company', default=lambda self: self.env.company, tracking=True)
    invoice_id = fields.Many2one(
        'account.move', string="Invoice/Bill", tracking=True)

    pdc_receivable_account_id = fields.Many2one(
        'account.account',
        string='Check Account',
        tracking=True
    )

    installment_no = fields.Char("Installment No", tracking=True)

    # UPDATED: Removed 'bounced' state and reordered
    state = fields.Selection([
        ('draft', 'Draft'),
        ('registered', 'Registered'),
        ('deposited', 'Deposited'),
        ('cashed', 'Cashed'),
        ('return', 'Return'),
        ('rejected', 'Rejected'),
        ('replaced', 'Replaced'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], string="State", default='draft', tracking=True)

    deposited_debit = fields.Many2one('account.move.line')
    deposited_credit = fields.Many2one('account.move.line')

    invoice_ids = fields.Many2many('account.move')
    account_move_ids = fields.Many2many(
        'account.move', compute="compute_account_moves", )
    done_date = fields.Date(string="Done Date", readonly=True, tracking=True)
    deposited_date = fields.Date(string="Deposit Date")

    # Return action fields
    return_action = fields.Selection([
        ('reject', 'Rejected'),
        ('replace', 'Replaced')
    ], string='Return Action', readonly=True, tracking=True)
    return_reason = fields.Text(string='Return Reason', readonly=True, tracking=True)
    old_reference = fields.Char(string='Old Cheque Reference', readonly=True, tracking=True)
    partner_bank_id = fields.Many2one(
        'res.partner.bank',
        string="Customer Bank Account",
        domain="[('partner_id', '=', partner_id)]",
        tracking=True
    )

    @api.depends('payment_type', 'partner_id')
    def compute_account_moves(self):

        self.account_move_ids = False
        domain = [('partner_id', '=', self.partner_id.id), ('payment_state', '!=',
                                                            'paid'), ('amount_residual', '!=', 0.0),
                  ('state', '=', 'posted')]

        if self.payment_type == 'receive_money':
            domain.extend([('move_type', '=', 'out_invoice')])

        else:
            domain.extend([('move_type', '=', 'in_invoice')])

        moves = self.env['account.move'].search(domain)
        self.account_move_ids = moves.ids

    @api.onchange('partner_id')
    def _onchange_partner(self):

        if self.env.company.auto_fill_open_invoice:

            domain = [('partner_id', '=', self.partner_id.id), ('payment_state', '!=',
                                                                'paid'), ('amount_residual', '!=', 0.0),
                      ('state', '=', 'posted')]

            if self.payment_type == 'receive_money':
                domain.extend([('move_type', '=', 'out_invoice')])

            else:
                domain.extend([('move_type', '=', 'in_invoice')])

            moves = self.env['account.move'].search(domain)

            self.invoice_ids = [(6, 0, moves.ids)]

    # Register pdc payment
    def button_register(self):
        self.ensure_one()
        self._check_reference_ready() 
        listt = []
        if self:

            if self.invoice_id:
                listt.append(self.invoice_id.id)
            if self.invoice_ids:
                listt.extend(self.invoice_ids.ids)

            self.write({
                'invoice_ids': [(6, 0, list(set(listt)))]
            })

            if self.cheque_status == 'draft':
                self.write({'state': 'draft'})

            if self.cheque_status == 'deposit':
                self.action_register()
                self.action_deposited()
                self.write({'state': 'deposited'})

            if self.cheque_status == 'paid':
                self.action_register()
                self.action_deposited()
                self.action_done()
                self.write({'state': 'done'})

    def action_register(self):
        self.ensure_one()
        self._check_reference_ready()
        move = self.env['account.move']

        self.check_payment_amount()

        if self.invoice_ids:
            list_amount_residuals = self.invoice_ids.mapped('amount_residual')
            amount = (self.currency_id.round(sum(list_amount_residuals))
                      if self.currency_id else round(sum(list_amount_residuals), 2))

            if self.payment_amount > amount and amount != 0:
                raise UserError(
                    "Payment amount is greater than total invoice/bill amount!!!")

        # Create journal entries when registering
        pdc_account = self.check_pdc_account()
        partner_account = self.get_partner_account()

        # Create Journal Item
        move_line_vals_debit = {}
        move_line_vals_credit = {}
        if self.payment_type == 'receive_money':
            move_line_vals_debit = self.get_debit_move_line(pdc_account)
            move_line_vals_credit = self.get_credit_move_line(partner_account)
        else:
            move_line_vals_debit = self.get_debit_move_line(partner_account)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)

        # create move and post it
        move_vals = self.get_move_vals(
            move_line_vals_debit, move_line_vals_credit)

        self.write({'state': 'registered'})

        # total_amount_residuals = sum(
        #     self.invoice_ids.mapped('amount_residual'))
        # if self.invoice_ids and total_amount_residuals != 0:
        move_id = move.create(move_vals)
        move_id.action_post()

        self.state = 'registered'

    def check_payment_amount(self):
        if self.payment_amount <= 0.0:
            raise UserError("Amount must be greater than zero!")

    def check_pdc_account(self):
        self.ensure_one()

        if self.pdc_receivable_account_id:
            return self.pdc_receivable_account_id.id

        if self.payment_type == 'receive_money':
            if not self.env.company.pdc_customer:
                raise UserError(
                    "Please Set PDC payment account for Customer !")
            else:
                return self.env.company.pdc_customer.id

        else:
            if not self.env.company.pdc_vendor:
                raise UserError(
                    "Please Set PDC payment account for Supplier !")
            else:
                return self.env.company.pdc_vendor.id

    def grt_undercollection_account(self):
        if not self.env.company.pdc_check_under_collection:
            raise UserError(
                "Please Set PDC payment account for Under Collection !")
        else:
            return self.env.company.pdc_check_under_collection.id

    def get_partner_account(self):
        if self.payment_type == 'receive_money':
            account = self.partner_id.property_account_receivable_id
        else:
            account = self.partner_id.property_account_payable_id
        if not account:
            raise UserError("Partner is missing a valid receivable or payable account.")
        return account.id

    def action_returned(self):
        """Move to Return state - user will choose reject or reset to draft"""
        self.check_payment_amount()
        self.write({'state': 'return'})

    def action_reject(self):
        """Reject the check - requires rejection reason"""
        self.ensure_one()
        self.check_payment_amount()
        # Validate reason is provided
        # if not self.return_reason or not self.return_reason.strip():
        #     raise UserError("Please provide a rejection reason before rejecting the check!")

        # Save old reference
        old_reference = self.reference
        move = self.env['account.move']

        ######## Reversed Registed
        # Create journal entries when registering
        pdc_account = self.check_pdc_account()
        partner_account = self.get_partner_account()
        pdc_under_collection = self.grt_undercollection_account()

        # Create Journal Item
        move_line_vals_debit = {}
        move_line_vals_credit = {}
        if self.payment_type == 'receive_money':
            move_line_vals_debit = self.get_debit_move_line(partner_account)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)
        else:
            move_line_vals_debit = self.get_debit_move_line(pdc_account)
            move_line_vals_credit = self.get_credit_move_line(partner_account)

        # create move and post it
        move_vals = self.get_move_vals(
            move_line_vals_debit, move_line_vals_credit)

        move_id = move.create(move_vals)
        move_id.action_post()

        ########Revresed Deposit

        # Create Journal Item
        move_line_vals_debit = {}
        move_line_vals_credit = {}
        if self.payment_type == 'receive_money':
            move_line_vals_debit = self.get_debit_move_line(pdc_account)
            move_line_vals_credit = self.get_credit_move_line(pdc_under_collection)
        else:
            move_line_vals_debit = self.get_debit_move_line(pdc_under_collection)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)

        # create move and post it
        move_vals = self.get_move_vals(
            move_line_vals_debit, move_line_vals_credit)

        move_id = move.create(move_vals)
        move_id.action_post()
        # Update to rejected state
        self.write({
            'state': 'rejected',
            'return_action': 'reject',
            'old_reference': old_reference,
            'payment_amount': 0.0,
        })

        # Post to chatter
        self.message_post(
            body=f"<b>Check Rejected</b><br/>Reason: {self.return_reason}<br/>Reference: {old_reference}",
            subject="Check Rejected"
        )

    def action_replace(self):
        """Replace check - saves record in replaced state, then creates new draft"""
        # Save old reference to prevent future duplication
        old_reference = self.reference
        self.ensure_one()
        self.check_payment_amount()

        move = self.env['account.move']

        ######## Reversed Registed
        # Create journal entries when registering
        pdc_account = self.check_pdc_account()
        partner_account = self.get_partner_account()
        pdc_under_collection = self.grt_undercollection_account()

        # Create Journal Item
        move_line_vals_debit = {}
        move_line_vals_credit = {}
        if self.payment_type == 'receive_money':
            move_line_vals_debit = self.get_debit_move_line(partner_account)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)
        else:
            move_line_vals_debit = self.get_debit_move_line(pdc_account)
            move_line_vals_credit = self.get_credit_move_line(partner_account)

        # create move and post it
        move_vals = self.get_move_vals(
            move_line_vals_debit, move_line_vals_credit)

        move_id = move.create(move_vals)
        move_id.action_post()

        ########Revresed Deposit

        # Create Journal Item
        move_line_vals_debit = {}
        move_line_vals_credit = {}
        if self.payment_type == 'receive_money':
            move_line_vals_debit = self.get_debit_move_line(pdc_account)
            move_line_vals_credit = self.get_credit_move_line(pdc_under_collection)
        else:
            move_line_vals_debit = self.get_debit_move_line(pdc_under_collection)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)

        # create move and post it
        move_vals = self.get_move_vals(
            move_line_vals_debit, move_line_vals_credit)

        move_id = move.create(move_vals)
        move_id.action_post()

        # 🔹 احفظ قيمة الفاتورة قبل تصفير الشيك
        invoice_amount = 0.0
        if self.invoice_ids:
            invoice_amount = sum(self.invoice_ids.mapped('amount_residual'))

        # 🔹 حدّث الشيك القديم (Replaced + صفر)
        self.write({
            'state': 'replaced',
            'old_reference': old_reference,
            'return_action': 'replace',
            'return_reason': False,
            'payment_amount': 0.0,
        })

        # 🔹 رسالة في الـ chatter
        self.message_post(
            body=f"<b>Check Replaced</b><br/>Old Reference: {old_reference or 'N/A'}",
            subject="Check Replaced"
        )

        # 🔹 إنشاء شيك جديد Draft بقيمة الفاتورة
        new_pdc = self.copy({
            'state': 'draft',
            'reference': '/',
            'old_reference': old_reference,
            'return_action': False,
            'return_reason': False,
            'deposited_date': False,
            'done_date': False,
            'payment_amount': invoice_amount,  # ⭐ هنا الحل
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'pdc.wizard',
            'res_id': new_pdc.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def get_debit_move_line(self, account):
        if not account:
            raise UserError("Missing debit account for PDC transaction.")
        return {
            'pdc_id': self.id,
            'account_id': account,
            'debit': self.payment_amount,
            'ref': self.memo,
            'date': self.payment_date,
            'date_maturity': self.due_date,
        }

    def get_credit_move_line(self, account):
        if not account:
            raise UserError("Missing credit account for PDC transaction.")
        return {
            'pdc_id': self.id,
            'account_id': account,
            'credit': self.payment_amount,
            'ref': self.memo,
            'date': self.payment_date,
            'date_maturity': self.due_date,
        }

    def get_move_vals(self, debit_line, credit_line):
        return {
            'pdc_id': self.id,
            'date': self.payment_date,
            'journal_id': self.journal_id.id,
            'partner_id': self.partner_id.id,
            'ref': self.memo,
            'move_type': 'entry',
            'line_ids': [(0, 0, debit_line),
                         (0, 0, credit_line)]
        }

    def action_deposited(self):
        self.ensure_one()
        self._check_reference_ready()
        move = self.env['account.move']

        self.check_payment_amount()

        if self.invoice_ids:
            list_amount_residuals = self.invoice_ids.mapped('amount_residual')
            amount = (self.currency_id.round(sum(list_amount_residuals))
                      if self.currency_id else round(sum(list_amount_residuals), 2))

            if self.payment_amount > amount and amount != 0:
                raise UserError(
                    "Payment amount is greater than total invoice/bill amount!!!")

        # Create journal entries when registering
        pdc_account = self.check_pdc_account()
        pdc_under_collection = self.grt_undercollection_account()

        # Create Journal Item
        move_line_vals_debit = {}
        move_line_vals_credit = {}
        if self.payment_type == 'receive_money':
            move_line_vals_debit = self.get_debit_move_line(pdc_under_collection)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)
        else:
            move_line_vals_debit = self.get_debit_move_line(pdc_account)
            move_line_vals_credit = self.get_credit_move_line(pdc_under_collection)

        # create move and post it
        move_vals = self.get_move_vals(
            move_line_vals_debit, move_line_vals_credit)

        move_id = move.create(move_vals)
        move_id.action_post()

        # if self.invoice_ids:
        #     for invoice in self.invoice_ids:
        #         receivable_lines = invoice.line_ids.filtered(
        #             lambda x: x.account_id.internal_group in ('asset_receivable', 'liability_payable')
        #         )
        #         if not receivable_lines:
        #             continue
        #
        #         register_move_lines = self.env['account.move.line'].search([
        #             ('pdc_id', '=', self.id),
        #             ('account_id', '=', receivable_lines[0].account_id.id),
        #             ('reconciled', '=', False)
        #         ])
        #
        #         aml_to_reconcile = (register_move_lines + invoice.line_ids).filtered(
        #             lambda l: l.account_id == receivable_lines[0].account_id and not l.reconciled
        #         )
        #
        #         if len(aml_to_reconcile) >= 2:
        #             aml_to_reconcile.reconcile()
        #
        #             # 🔥 FORCE In Payment (Odoo 18)
        #             invoice.invalidate_cache()
        #             invoice.sudo().write({'payment_state': 'in_payment'})

        self.write({'state': 'deposited'})

    def action_cashed(self):
        self.ensure_one()
        self._check_reference_ready()
        Move = self.env['account.move']

        self.check_payment_amount()

        # حساب PDC
        pdc_account = self.check_pdc_account()

        # حساب البنك أو النقدي
        if self.journal_id:
            if self.journal_id.type in ['bank', 'cash']:
                if not self.journal_id.default_account_id:
                    raise UserError(f"Please configure a default account on the journal: {self.journal_id.name}")
                bank_account = self.journal_id.default_account_id.id
            else:
                raise UserError("Journal type must be 'bank' or 'cash'")

        # إنشاء سطور القيد
        if self.payment_type == 'receive_money':
            debit_line = self.get_debit_move_line(bank_account)
            credit_line = self.get_credit_move_line(pdc_account)
        else:
            debit_line = self.get_debit_move_line(pdc_account)
            credit_line = self.get_credit_move_line(bank_account)

        move_vals = self.get_move_vals(debit_line, credit_line)
        move = Move.create(move_vals)
        move.action_post()

        # 🔁 Reconcile فقط لو فيه فواتير
        if self.invoice_ids:
            for invoice in self.invoice_ids:
                receivable_lines = invoice.line_ids.filtered(
                    lambda x: x.account_id.internal_group in ('asset_receivable', 'liability_payable')
                )
                if not receivable_lines:
                    continue
                aml_to_reconcile = (move.line_ids + invoice.line_ids).filtered(
                    lambda l: l.account_id == receivable_lines[0].account_id and not l.reconciled
                )
                if len(aml_to_reconcile) >= 2:
                    aml_to_reconcile.reconcile()

        self.write({
            'state': 'cashed',
            'done_date': fields.Date.context_today(self),
        })

    def action_done(self):
        self.ensure_one()
        self._check_reference_ready()
        Move = self.env['account.move']

        self.check_payment_amount()

        # حساب البنك أو النقدي
        if self.journal_id:
            if self.journal_id.type in ['bank', 'cash']:
                if not self.journal_id.default_account_id:
                    raise UserError(f"Please configure a default account on the journal: {self.journal_id.name}")
                bank_account = self.journal_id.default_account_id.id
            else:
                raise UserError("Journal type must be 'bank' or 'cash'")

        pdc_under_collection = self.grt_undercollection_account()
        if self.payment_type == 'receive_money':
            debit_line = self.get_debit_move_line(bank_account)
            credit_line = self.get_credit_move_line(pdc_under_collection)
        else:
            debit_line = self.get_debit_move_line(pdc_under_collection)
            credit_line = self.get_credit_move_line(bank_account)

        move_vals = self.get_move_vals(debit_line, credit_line)
        move = Move.create(move_vals)
        move.action_post()

        # 🔁 Reconcile فقط لو فيه فواتير
        if self.invoice_ids:
            for invoice in self.invoice_ids:
                receivable_lines = invoice.line_ids.filtered(
                    lambda x: x.account_id.internal_group in ('asset_receivable', 'liability_payable')
                )
                if not receivable_lines:
                    continue
                aml_to_reconcile = (move.line_ids + invoice.line_ids).filtered(
                    lambda l: l.account_id == receivable_lines[0].account_id and not l.reconciled
                )
                if len(aml_to_reconcile) >= 2:
                    aml_to_reconcile.reconcile()

        self.write({
            'state': 'done',
            'done_date': fields.Date.context_today(self),
        })

    # form view cancel button
    def action_cancel(self):
        self.action_delete_related_moves()
        # self._remove_pdc_effect_from_invoices()
        if self.company_id.pdc_operation_type == 'cancel':
            self.write({'state': 'cancel'})

        elif self.company_id.pdc_operation_type == 'cancel_draft':
            self.write({'state': 'draft'})

        elif self.company_id.pdc_operation_type == 'cancel_delete':
            self.write({'state': 'draft'})
            self.unlink()
            return {'type': 'ir.actions.act_window_close'}

    # multi action methods
    def action_pdc_cancel(self):
        self.action_delete_related_moves()
        self.write({'state': 'cancel'})

    def action_pdc_cancel_draft(self):
        self.action_delete_related_moves()
        self.write({'state': 'draft'})

    def action_pdc_cancel_delete(self):
        self.action_delete_related_moves()
        self.write({'state': 'draft'})
        self.unlink()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('payment_type') == 'receive_money':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'pdc.payment.customer')
            elif vals.get('payment_type') == 'send_money':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'pdc.payment.vendor')

        res = super().create(vals_list)
        res.attachment_ids.write({
            'res_id': res.id
        })
        return res

    # ==============================
    #    CRON SCHEDULER CUSTOMER
    # ==============================
    @api.model
    def notify_customer_due_date(self):
        emails = []
        if self.env.company.is_cust_due_notify:
            notify_day_1 = self.env.company.notify_on_1
            notify_day_2 = self.env.company.notify_on_2
            notify_day_3 = self.env.company.notify_on_3
            notify_day_4 = self.env.company.notify_on_4
            notify_day_5 = self.env.company.notify_on_5
            notify_date_1 = False
            notify_date_2 = False
            notify_date_3 = False
            notify_date_4 = False
            notify_date_5 = False
            if notify_day_1:
                notify_date_1 = fields.date.today() + timedelta(days=int(notify_day_1) * -1)
            if notify_day_2:
                notify_date_2 = fields.date.today() + timedelta(days=int(notify_day_2) * -1)
            if notify_day_3:
                notify_date_3 = fields.date.today() + timedelta(days=int(notify_day_3) * -1)
            if notify_day_4:
                notify_date_4 = fields.date.today() + timedelta(days=int(notify_day_4) * -1)
            if notify_day_5:
                notify_date_5 = fields.date.today() + timedelta(days=int(notify_day_5) * -1)

            records = self.search([('payment_type', '=', 'receive_money')])
            for user in self.env.company.sh_user_ids:
                if user.partner_id and user.partner_id.email:
                    emails.append(user.partner_id.email)
            email_values = {
                'email_to': ','.join(emails),
            }
            view = self.env.ref("sh_pdc.sh_pdc_payment_form_view",
                                raise_if_not_found=False).sudo()
            view_id = view.id if view else 0
            for record in records:
                if (record.due_date == notify_date_1
                        or record.due_date == notify_date_2
                        or record.due_date == notify_date_3
                        or record.due_date == notify_date_4
                        or record.due_date == notify_date_5):

                    if self.env.company.is_notify_to_customer:
                        template_download_id = self.env.ref(
                            'sh_pdc.sh_pdc_company_to_customer_notification_1')
                        _ = record.env['mail.template'].browse(
                            template_download_id.id
                        ).send_mail(record.id, email_layout_xmlid='mail.mail_notification_light', force_send=True)
                    if self.env.company.is_notify_to_user and self.env.company.sh_user_ids:
                        url = ''
                        base_url = request.env['ir.config_parameter'].sudo(
                        ).get_param('web.base.url')
                        url = base_url + "/web#id=" + \
                              str(record.id) + \
                              "&&model=pdc.wizard&view_type=form&view_id=" + \
                              str(view_id)
                        ctx = {
                            "customer_url": url,
                        }
                        template_download_id = self.env.ref(
                            'sh_pdc.sh_pdc_company_to_int_user_notification_1')
                        _ = request.env['mail.template'].sudo().browse(template_download_id.id).with_context(
                            ctx).send_mail(
                            record.id, email_values=email_values, email_layout_xmlid='mail.mail_notification_light',
                            force_send=True)

    # Multi Action Starts for change the state of PDC check

    def action_set_draft(self):
        for rec in self:
            moves = self.env['account.move'].search([('pdc_id', '=', rec.id)])
            for move in moves:
                if move.state == 'posted':
                    move.button_draft()
        self.sudo().write({
            'state': 'draft',
        })

    def action_delete_related_moves(self):
        for model in self:
            model.payment_amount = 0.0
            move_ids = self.env['account.move'].search(
                [('pdc_id', '=', model.id)])
            for move in move_ids:
                move.button_draft()
                lines = self.env['account.move.line'].search(
                    [('move_id', '=', move.id)])
                lines.unlink()

            model.sudo().write({
                'done_date': False
            })

            for move in move_ids:
                self.env.cr.execute(
                    """ delete from account_move where id =%s""" % (move.id,))

    def action_state_register(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'draft':
                    for active_model in active_models:
                        active_model.action_register()
                else:
                    raise UserError(
                        "Only Draft state PDC check can switch to Register state!!")
            else:
                raise UserError(
                    "States must be same!!")

    def action_state_return(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'registered':
                    for active_model in active_models:
                        active_model.action_returned()
                else:
                    raise UserError(
                        "Only Register state PDC check can switch to return state!!")
            else:
                raise UserError(
                    "States must be same!!")

    # UPDATED: Removed 'bounced' from allowed states
    def action_state_deposit(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] in ['registered', 'returned']:
                    for active_model in active_models:
                        active_model.action_deposited()
                else:
                    raise UserError(
                        "Only Register and Return state PDC check can switch to Deposit state!!")
            else:
                raise UserError(
                    "States must be same!!")

    # REMOVED: action_state_bounce() method - no longer needed

    def action_state_done(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'deposited':
                    for active_model in active_models:
                        active_model.action_done()
                else:
                    raise UserError(
                        "Only Deposit state PDC check can switch to Done state!!")
            else:
                raise UserError(
                    "States must be same!!")

    # UPDATED: Removed 'bounced' from allowed states
    def action_state_cancel(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] in ['registered', 'returned']:
                    for active_model in active_models:
                        active_model.action_cancel()
                else:
                    raise UserError(
                        "Only Register and Return state PDC check can switch to Cancel state!!")
            else:
                raise UserError(
                    "States must be same!!")

    def _remove_pdc_effect_from_invoices(self):
        """
        Remove PDC amount from related invoices
        and delete cancelled PDC journal lines
        """
        for rec in self:
            if not rec.invoice_ids:
                continue

            for invoice in rec.invoice_ids:

                # 🔹 فك أي Reconciliation مرتبط بالشيك
                pdc_lines = self.env['account.move.line'].search([
                    ('pdc_id', '=', rec.id),
                    ('reconciled', '=', True)
                ])

                for line in pdc_lines:
                    if line.reconciled:
                        line.remove_move_reconcile()

                # 🔹 حذف سطور القيود المرتبطة بالشيك
                move_lines = self.env['account.move.line'].search([
                    ('pdc_id', '=', rec.id)
                ])
                move_lines.unlink()

            # 🔹 حذف القيود نفسها
            moves = self.env['account.move'].search([
                ('pdc_id', '=', rec.id)
            ])

            for move in moves:
                if move.state == 'posted':
                    move.button_draft()
                move.unlink()
