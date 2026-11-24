# -*- coding: utf-8 -*-
from markupsafe import Markup
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class ConstructionCertificate(models.Model):
    _name = 'construction.certificate'
    _description = 'مستخلص أعمال (مقاول / عميل)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    @api.model
    def _default_sar_currency(self):
        sar = self.env['res.currency'].search(
            [('name', '=', 'SAR'), ('active', '=', True)], limit=1
        )
        return sar or self.env.company.currency_id

    name = fields.Char(
        string='المرجع',
        required=True,
        copy=False,
        readonly=True,
        default='جديد',
    )
    certificate_no = fields.Char(
        string='رقم المستخلص',
        tracking=True,
        help='مثال: جاري رقم / 12',
    )
    certificate_type = fields.Selection(
        [
            ('vendor', 'مستخلص مقاول / باطن'),
            ('customer', 'مستخلص عميل خارجي'),
        ],
        string='نوع المستخلص',
        default='vendor',
        required=True,
        tracking=True,
    )
    project_id = fields.Many2one(
        'project.project',
        string='المشروع',
        required=True,
        tracking=True,
    )
    boq_id = fields.Many2one(
        'construction.boq',
        string='المقايسة المرتبطة',
        domain="[('project_id', '=', project_id)]",
        tracking=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='المقاول / العميل',
        required=True,
        tracking=True,
    )
    work_scope = fields.Char(
        string='بند العمل',
        tracking=True,
        help='مثال: مصنعية أعمال العظم',
    )
    date = fields.Date(
        string='التاريخ',
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='الشركة',
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='العملة',
        default=_default_sar_currency,
        required=True,
        tracking=True,
    )

    # Bank & Subcontract Reference
    bank_name = fields.Char(string='البنك')
    bank_account_no = fields.Char(string='رقم الحساب')
    iban = fields.Char(string='الآيبان (IBAN)')
    contract_ref = fields.Char(string='مرجع العقد / أمر الشراء')
    subcontract_file = fields.Binary(string='مرفق عقد المقاول', attachment=True)
    subcontract_filename = fields.Char(string='اسم ملف العقد')
    notes = fields.Text(string='ملاحظات')

    # Workflow & Approvals
    state = fields.Selection(
        [
            ('draft', 'مسودة'),
            ('site_engineer', 'مراجعة مهندس الموقع'),
            ('pm_approved', 'معتمد من مدير المشروع'),
            ('accounting', 'مراجعة المالية'),
            ('paid', 'تم الصرف / التحصيل'),
            ('rejected', 'مرفوض'),
        ],
        string='الحالة',
        default='draft',
        required=True,
        tracking=True,
    )
    rejection_reason = fields.Text(string='سبب الرفض', tracking=True)
    site_engineer_id = fields.Many2one(
        'res.users',
        string='مراجعة مهندس الموقع / حاسب الكميات',
        readonly=True,
        copy=False,
    )
    pm_approved_by_id = fields.Many2one(
        'res.users',
        string='اعتماد مدير المشروع',
        readonly=True,
        copy=False,
    )
    accounting_approved_by_id = fields.Many2one(
        'res.users',
        string='اعتماد المالية',
        readonly=True,
        copy=False,
    )
    move_id = fields.Many2one(
        'account.move',
        string='الفاتورة المحاسبية المرتبطة',
        readonly=True,
        copy=False,
    )
    move_state = fields.Selection(
        related='move_id.state',
        string='حالة الفاتورة',
        readonly=True,
    )

    # Lines
    line_ids = fields.One2many(
        'construction.certificate.line',
        'certificate_id',
        string='بنود الأعمال والحصر',
    )

    # Financial Summary & Retention Inputs
    retention_percent = fields.Float(
        string='نسبة محجوز ضمان حسن الأداء (%)',
        default=10.0,
        digits=(5, 2),
        tracking=True,
    )
    deduction_prev = fields.Monetary(
        string='إجمالي الخصم السابق',
        currency_field='currency_id',
        default=0.0,
    )
    deduction_curr = fields.Monetary(
        string='إجمالي الخصم الحالي',
        currency_field='currency_id',
        default=0.0,
    )
    deduction_cumul = fields.Monetary(
        string='إجمالي الخصم التراكمي',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    previously_paid = fields.Monetary(
        string='ما سبق صرفه حتى تاريخه',
        currency_field='currency_id',
        default=0.0,
    )

    # Computed Gross Totals
    contract_total = fields.Monetary(
        string='قيمة التعاقد الإجمالية',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    prev_total = fields.Monetary(
        string='القيمة الإجمالية (السابق)',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    curr_total = fields.Monetary(
        string='القيمة الإجمالية (الحالي)',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    cumul_total = fields.Monetary(
        string='القيمة الإجمالية (التراكمي)',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    remaining_total = fields.Monetary(
        string='القيمة المتبقية',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )

    # Computed Retention & Net Totals
    retention_prev = fields.Monetary(
        string='محجوز الضمان (السابق)',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    retention_curr = fields.Monetary(
        string='محجوز الضمان (الحالي)',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    retention_cumul = fields.Monetary(
        string='محجوز الضمان (التراكمي)',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    after_retention_prev = fields.Monetary(
        string='بعد محجوز الضمان (السابق)',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    after_retention_curr = fields.Monetary(
        string='بعد محجوز الضمان (الحالي)',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    after_retention_cumul = fields.Monetary(
        string='بعد محجوز الضمان (التراكمي)',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    after_deduction_prev = fields.Monetary(
        string='بعد الخصم (السابق)',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    after_deduction_curr = fields.Monetary(
        string='بعد الخصم (الحالي)',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    after_deduction_cumul = fields.Monetary(
        string='بعد الخصم (التراكمي)',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    prev_settlement_diff = fields.Monetary(
        string='فرق تسوية ما سبق صرفه',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    net_payable_curr = fields.Monetary(
        string='صافي المبلغ المستحق صرفه للمستخلص الحالي',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    overall_progress_percent = fields.Float(
        string='نسبة الإنجاز الكلية (%)',
        compute='_compute_totals',
        store=True,
        digits=(5, 2),
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == 'جديد':
                cert_type = vals.get('certificate_type') or self.env.context.get(
                    'default_certificate_type', 'vendor'
                )
                seq_code = (
                    'construction.certificate.customer'
                    if cert_type == 'customer'
                    else 'construction.certificate.vendor'
                )
                fallback = 'CERT/C/2026/001' if cert_type == 'customer' else 'CERT/V/2026/001'
                vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or fallback
        return super().create(vals_list)

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id:
            if self.project_id.stm_boq_id:
                self.boq_id = self.project_id.stm_boq_id
            else:
                boq = self.env['construction.boq'].search(
                    [('project_id', '=', self.project_id.id)], limit=1
                )
                self.boq_id = boq.id if boq else False
            if self.certificate_type == 'customer' and not self.partner_id and self.project_id.partner_id:
                self.partner_id = self.project_id.partner_id

    @api.depends(
        'line_ids.display_type',
        'line_ids.contract_total',
        'line_ids.prev_total',
        'line_ids.curr_total',
        'line_ids.cumul_total',
        'line_ids.remaining_total',
        'retention_percent',
        'deduction_prev',
        'deduction_curr',
        'previously_paid',
    )
    def _compute_totals(self):
        for rec in self:
            work_lines = rec.line_ids.filtered(lambda l: not l.display_type)
            contract_total = sum(work_lines.mapped('contract_total'))
            prev_total = sum(work_lines.mapped('prev_total'))
            curr_total = sum(work_lines.mapped('curr_total'))
            cumul_total = sum(work_lines.mapped('cumul_total'))
            remaining_total = sum(work_lines.mapped('remaining_total'))

            rate = (rec.retention_percent or 0.0) / 100.0
            ret_prev = prev_total * rate
            ret_curr = curr_total * rate
            ret_cumul = cumul_total * rate

            after_ret_prev = prev_total - ret_prev
            after_ret_curr = curr_total - ret_curr
            after_ret_cumul = cumul_total - ret_cumul

            ded_prev = rec.deduction_prev or 0.0
            ded_curr = rec.deduction_curr or 0.0
            ded_cumul = ded_prev + ded_curr

            after_ded_prev = after_ret_prev - ded_prev
            after_ded_curr = after_ret_curr - ded_curr
            after_ded_cumul = after_ret_cumul - ded_cumul

            prev_paid = rec.previously_paid or 0.0
            prev_diff = (after_ded_prev - prev_paid) if prev_paid else 0.0
            net_curr = (after_ded_cumul - prev_paid) if prev_paid else after_ded_curr

            rec.contract_total = contract_total
            rec.prev_total = prev_total
            rec.curr_total = curr_total
            rec.cumul_total = cumul_total
            rec.remaining_total = remaining_total

            rec.retention_prev = ret_prev
            rec.retention_curr = ret_curr
            rec.retention_cumul = ret_cumul

            rec.after_retention_prev = after_ret_prev
            rec.after_retention_curr = after_ret_curr
            rec.after_retention_cumul = after_ret_cumul

            rec.deduction_cumul = ded_cumul
            rec.after_deduction_prev = after_ded_prev
            rec.after_deduction_curr = after_ded_curr
            rec.after_deduction_cumul = after_ded_cumul

            rec.prev_settlement_diff = prev_diff
            rec.net_payable_curr = net_curr
            rec.overall_progress_percent = (
                (cumul_total / contract_total) * 100.0 if contract_total > 0.0 else 0.0
            )

    def action_load_from_boq(self):
        for rec in self:
            if not rec.boq_id:
                raise UserError('يرجى تحديد المقايسة المرتبطة أولاً لاستيراد البنود.')
            existing_boq_line_ids = set(
                rec.line_ids.filtered('boq_line_id').mapped('boq_line_id').ids
            )
            seq = (max(rec.line_ids.mapped('sequence') or [0])) + 10
            vals_to_add = []
            for idx, boq_line in enumerate(rec.boq_id.line_ids.filtered('included'), start=1):
                if boq_line.id in existing_boq_line_ids:
                    continue
                vals_to_add.append(
                    (
                        0,
                        0,
                        {
                            'sequence': seq,
                            'item_code': str(idx),
                            'name': boq_line.name,
                            'uom_name': boq_line.uom_name or 'مقطوعة',
                            'contract_qty': boq_line.planned_qty or 1.0,
                            'unit_price': boq_line.unit_price or 0.0,
                            'is_variation_order': boq_line.is_variation_order,
                            'boq_line_id': boq_line.id,
                        },
                    )
                )
                seq += 10
            if not vals_to_add:
                raise UserError('تم استيراد جميع بنود المقايسة المشمولة مسبقاً أو لا توجد بنود.')
            rec.write({'line_ids': vals_to_add})
        return True

    def action_pull_previous_certificate(self):
        for rec in self:
            domain = [
                ('id', '!=', rec.id),
                ('project_id', '=', rec.project_id.id),
                ('partner_id', '=', rec.partner_id.id),
                ('certificate_type', '=', rec.certificate_type),
                ('state', 'in', ('pm_approved', 'accounting', 'paid')),
            ]
            prev_cert = self.search(domain, order='date desc, id desc', limit=1)
            if not prev_cert:
                raise UserError(
                    'لا يوجد مستخلص سابق معتمد لنفس المشروع والطرف ونفس النوع لجلب الكميات منه.'
                )

            if not rec.line_ids:
                new_lines = []
                for pl in prev_cert.line_ids:
                    new_lines.append(
                        (
                            0,
                            0,
                            {
                                'sequence': pl.sequence,
                                'display_type': pl.display_type,
                                'is_variation_order': pl.is_variation_order,
                                'item_code': pl.item_code,
                                'name': pl.name,
                                'uom_name': pl.uom_name,
                                'boq_line_id': pl.boq_line_id.id if pl.boq_line_id else False,
                                'contract_qty': pl.contract_qty,
                                'unit_price': pl.unit_price,
                                'prev_qty': 0.0 if pl.display_type else pl.cumul_qty,
                                'curr_qty': 0.0,
                            },
                        )
                    )
                rec.write({'line_ids': new_lines})
            else:
                by_boq_line = {
                    pl.boq_line_id.id: pl.cumul_qty
                    for pl in prev_cert.line_ids
                    if not pl.display_type and pl.boq_line_id
                }
                by_name = {
                    (pl.name or '').strip(): pl.cumul_qty
                    for pl in prev_cert.line_ids
                    if not pl.display_type
                }
                for line in rec.line_ids.filtered(lambda l: not l.display_type):
                    if line.boq_line_id and line.boq_line_id.id in by_boq_line:
                        line.prev_qty = by_boq_line[line.boq_line_id.id]
                    elif (line.name or '').strip() in by_name:
                        line.prev_qty = by_name[(line.name or '').strip()]

            rec.write(
                {
                    'deduction_prev': prev_cert.deduction_cumul,
                    'previously_paid': prev_cert.after_deduction_cumul,
                }
            )
            rec.message_post(
                body=Markup(
                    "تم جلب الكميات السابقة وما سبق صرفه من المستخلص السابق <b>%s</b>."
                ) % (prev_cert.certificate_no or prev_cert.name)
            )
        return True

    def action_submit_engineering(self):
        for rec in self:
            work_lines = rec.line_ids.filtered(lambda l: not l.display_type)
            if not work_lines:
                raise UserError('يرجى إدخال بند أعمال واحد على الأقل قبل إرسال المستخلص.')
            rec.write(
                {
                    'state': 'site_engineer',
                    'site_engineer_id': self.env.user.id,
                    'rejection_reason': False,
                }
            )
            rec.message_post(body='تم إرسال المستخلص للمراجعة الهندسية وحصر الكميات.')
        return True

    def action_pm_approve(self):
        for rec in self:
            rec.write(
                {
                    'state': 'pm_approved',
                    'pm_approved_by_id': self.env.user.id,
                }
            )
            rec.message_post(body='تم اعتماد المستخلص من مدير المشروع.')
        return True

    def action_send_accounting(self):
        for rec in self:
            rec.write({'state': 'accounting'})
            rec.message_post(body='تم إرسال المستخلص للمراجعة المالية والحسابات.')
        return True

    def action_mark_paid(self):
        for rec in self:
            rec.write(
                {
                    'state': 'paid',
                    'accounting_approved_by_id': self.env.user.id,
                }
            )
            rec.message_post(body='تم اعتماد الصرف / التحصيل وإغلاق المستخلص.')
        return True

    def action_reject(self):
        for rec in self:
            if not (rec.rejection_reason or '').strip():
                raise UserError('يرجى كتابة سبب الرفض في حقل «سبب الرفض» قبل رفض المستخلص.')
            rec.write({'state': 'rejected'})
            rec.message_post(body=f'تم رفض المستخلص. السبب: {rec.rejection_reason}')
        return True

    def action_reset_draft(self):
        self.write({'state': 'draft'})
        return True

    def _resolve_certificate_journal_and_account(self, move_type):
        self.ensure_one()
        journal_type = 'purchase' if move_type == 'in_invoice' else 'sale'
        journal = self.env['account.journal'].search(
            [('company_id', '=', self.company_id.id), ('type', '=', journal_type)],
            limit=1,
        )
        if not journal:
            raise UserError(
                f"لم يتم العثور على دفتر يومية من نوع ({journal_type}) للشركة {self.company_id.name}."
            )

        account_types = (
            ['expense_direct_cost', 'expense']
            if move_type == 'in_invoice'
            else ['income', 'income_other']
        )
        account = self.env['account.account'].search(
            [
                ('company_ids', 'in', [self.company_id.id]),
                ('account_type', 'in', account_types),
            ],
            order='code asc',
            limit=1,
        )
        if not account:
            raise UserError(
                'لم يتم العثور على حساب مصروفات/إيرادات مناسب في شجرة الحسابات لإنشاء الفاتورة.'
            )
        return journal, account

    def action_create_account_move(self):
        self.ensure_one()
        if self.state not in ('pm_approved', 'accounting', 'paid'):
            raise UserError('يجب اعتماد المستخلص من مدير المشروع أولاً قبل إنشاء المسودة المحاسبية.')
        if self.move_id:
            return self.action_view_account_move()
        if self.curr_total <= 0 and self.net_payable_curr <= 0:
            raise UserError('لا توجد قيمة حالية مستحقة لإنشاء فاتورة محاسبية.')

        move_type = 'in_invoice' if self.certificate_type == 'vendor' else 'out_invoice'
        journal, account = self._resolve_certificate_journal_and_account(move_type)

        analytic_distribution = False
        if self.project_id and 'account_id' in self.project_id._fields and self.project_id.account_id:
            analytic_distribution = {str(self.project_id.account_id.id): 100}

        def _make_line(label, amount):
            vals = {
                'name': label,
                'account_id': account.id,
                'quantity': 1.0,
                'price_unit': amount,
                'tax_ids': [(5, 0, 0)],
            }
            if analytic_distribution:
                vals['analytic_distribution'] = analytic_distribution
            return (0, 0, vals)

        invoice_lines = [
            _make_line(
                f"قيمة الأعمال الحالية — {self.work_scope or self.name}",
                self.curr_total,
            )
        ]
        if self.retention_curr > 0:
            invoice_lines.append(
                _make_line(
                    f"استقطاع محجوز ضمان حسن الأداء ({self.retention_percent:.1f}%)",
                    -self.retention_curr,
                )
            )
        if self.deduction_curr > 0:
            invoice_lines.append(
                _make_line('خصومات مستخلص جاري', -self.deduction_curr)
            )
        if self.previously_paid > 0 and abs(self.prev_settlement_diff) > 0.01:
            invoice_lines.append(
                _make_line('تسوية فروق مستخلصات سابقة', self.prev_settlement_diff)
            )

        ref_parts = [p for p in [self.name, self.certificate_no] if p]
        move_vals = {
            'move_type': move_type,
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'journal_id': journal.id,
            'currency_id': self.currency_id.id,
            'invoice_date': self.date,
            'ref': ' - '.join(ref_parts),
            'stm_certificate_id': self.id,
            'invoice_line_ids': invoice_lines,
        }
        move = self.env['account.move'].create(move_vals)

        write_vals = {'move_id': move.id, 'accounting_approved_by_id': self.env.user.id}
        if self.state == 'pm_approved':
            write_vals['state'] = 'accounting'
        self.write(write_vals)

        bill_label = 'مسودة فاتورة مورد' if move_type == 'in_invoice' else 'مسودة فاتورة عميل'
        self.message_post(
            body=Markup("تم إنشاء %s رقم <b>%s</b>.") % (bill_label, move.name or move.id)
        )
        return self.action_view_account_move()

    def action_view_account_move(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError('لا توجد فاتورة محاسبية مرتبطة بهذا المستخلص بعد.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'الفاتورة المحاسبية',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
        }

    def action_print_certificate_pdf(self):
        self.ensure_one()
        return self.env.ref(
            'stm_construction_demo.action_report_construction_certificate'
        ).report_action(self)


class ConstructionCertificateLine(models.Model):
    _name = 'construction.certificate.line'
    _description = 'بند مستخلص الأعمال'
    _order = 'sequence, id'

    certificate_id = fields.Many2one(
        'construction.certificate',
        string='المستخلص',
        required=True,
        ondelete='cascade',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='certificate_id.currency_id',
        store=True,
        readonly=True,
    )
    sequence = fields.Integer(string='م', default=10)
    display_type = fields.Selection(
        [
            ('line_section', 'قسم'),
            ('line_note', 'ملاحظة'),
        ],
        string='نوع السطر',
        default=False,
    )
    is_variation_order = fields.Boolean(string='أمر تغييري', default=False)
    item_code = fields.Char(string='رقم البند')
    name = fields.Char(string='وصف الأعمال', required=True)
    uom_name = fields.Char(string='الوحدة', default='مقطوعة')
    boq_line_id = fields.Many2one('construction.boq.line', string='بند المقايسة')

    # Contract
    contract_qty = fields.Float(string='كمية التعاقد', default=0.0, digits=(12, 2))
    unit_price = fields.Monetary(string='السعر', currency_field='currency_id', default=0.0)
    contract_total = fields.Monetary(
        string='إجمالي التعاقد',
        currency_field='currency_id',
        compute='_compute_line_values',
        store=True,
    )

    # Previous
    prev_qty = fields.Float(string='الكمية السابقة', default=0.0, digits=(12, 2))
    prev_pct = fields.Float(
        string='نسبة السابق %',
        compute='_compute_line_values',
        store=True,
        digits=(5, 2),
    )
    prev_total = fields.Monetary(
        string='إجمالي السابق',
        currency_field='currency_id',
        compute='_compute_line_values',
        store=True,
    )

    # Current
    curr_qty = fields.Float(string='الكمية الحالية', default=0.0, digits=(12, 2))
    curr_pct = fields.Float(
        string='نسبة الحالي %',
        compute='_compute_line_values',
        store=True,
        digits=(5, 2),
    )
    curr_total = fields.Monetary(
        string='إجمالي الحالي',
        currency_field='currency_id',
        compute='_compute_line_values',
        store=True,
    )

    # Cumulative
    cumul_qty = fields.Float(
        string='الكمية التراكمية',
        compute='_compute_line_values',
        store=True,
        digits=(12, 2),
    )
    cumul_pct = fields.Float(
        string='النسبة التراكمية %',
        compute='_compute_line_values',
        store=True,
        digits=(5, 2),
    )
    cumul_total = fields.Monetary(
        string='الإجمالي التراكمي',
        currency_field='currency_id',
        compute='_compute_line_values',
        store=True,
    )

    # Remaining
    remaining_qty = fields.Float(
        string='الكمية المتبقية',
        compute='_compute_line_values',
        store=True,
        digits=(12, 2),
    )
    remaining_pct = fields.Float(
        string='النسبة المتبقية %',
        compute='_compute_line_values',
        store=True,
        digits=(5, 2),
    )
    remaining_total = fields.Monetary(
        string='الإجمالي المتبقي',
        currency_field='currency_id',
        compute='_compute_line_values',
        store=True,
    )

    @api.depends('display_type', 'contract_qty', 'unit_price', 'prev_qty', 'curr_qty')
    def _compute_line_values(self):
        for line in self:
            if line.display_type:
                line.contract_total = 0.0
                line.prev_pct = 0.0
                line.prev_total = 0.0
                line.curr_pct = 0.0
                line.curr_total = 0.0
                line.cumul_qty = 0.0
                line.cumul_pct = 0.0
                line.cumul_total = 0.0
                line.remaining_qty = 0.0
                line.remaining_pct = 0.0
                line.remaining_total = 0.0
                continue

            c_qty = line.contract_qty or 0.0
            price = line.unit_price or 0.0
            p_qty = line.prev_qty or 0.0
            cur_qty = line.curr_qty or 0.0

            cum_qty = p_qty + cur_qty
            rem_qty = c_qty - cum_qty

            line.contract_total = c_qty * price
            line.prev_total = p_qty * price
            line.curr_total = cur_qty * price
            line.cumul_qty = cum_qty
            line.cumul_total = cum_qty * price
            line.remaining_qty = rem_qty
            line.remaining_total = rem_qty * price

            if c_qty > 0.0:
                line.prev_pct = (p_qty / c_qty) * 100.0
                line.curr_pct = (cur_qty / c_qty) * 100.0
                line.cumul_pct = (cum_qty / c_qty) * 100.0
                line.remaining_pct = (rem_qty / c_qty) * 100.0
            else:
                line.prev_pct = 0.0
                line.curr_pct = 0.0
                line.cumul_pct = 0.0
                line.remaining_pct = 0.0

    @api.constrains('contract_qty', 'prev_qty', 'curr_qty', 'display_type')
    def _check_over_contract_qty(self):
        for line in self:
            if line.display_type:
                continue
            if line.contract_qty > 0.0 and (line.prev_qty + line.curr_qty) > (line.contract_qty + 1e-6):
                cum_qty = line.prev_qty + line.curr_qty
                raise ValidationError(
                    f"لا يمكن تجاوز الكمية التعاقدية في البند ({line.name}) — "
                    f"التراكمي ({cum_qty:.2f}) أكبر من التعاقد ({line.contract_qty:.2f}). "
                    f"يرجى تعديل الكمية الحالية أو إصدار أمر تغييري."
                )


class AccountMoveCertificateInherit(models.Model):
    _inherit = 'account.move'

    stm_certificate_id = fields.Many2one(
        'construction.certificate',
        string='المستخلص المرتبط',
        readonly=True,
        copy=False,
    )

    def action_view_stm_certificate(self):
        self.ensure_one()
        if not self.stm_certificate_id:
            raise UserError('لا يوجد مستخلص مرتبط بهذه الفاتورة.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'المستخلص المرتبط',
            'res_model': 'construction.certificate',
            'view_mode': 'form',
            'res_id': self.stm_certificate_id.id,
        }


class ProjectProjectCertInherit(models.Model):
    _inherit = 'project.project'

    stm_certificate_count = fields.Integer(
        string='المستخلصات',
        compute='_compute_stm_certificate_count',
    )

    def _compute_stm_certificate_count(self):
        Certificate = self.env['construction.certificate']
        for rec in self:
            rec.stm_certificate_count = Certificate.search_count([('project_id', '=', rec.id)])

    def action_view_stm_certificates(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'المستخلصات',
            'res_model': 'construction.certificate',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
                'default_boq_id': self.stm_boq_id.id if self.stm_boq_id else False,
            },
        }


class ConstructionBoqCertInherit(models.Model):
    _inherit = 'construction.boq'

    certificate_count = fields.Integer(
        string='المستخلصات',
        compute='_compute_certificate_count',
    )

    def _compute_certificate_count(self):
        Certificate = self.env['construction.certificate']
        for rec in self:
            domain = (
                ['|', ('boq_id', '=', rec.id), ('project_id', '=', rec.project_id.id)]
                if rec.project_id
                else [('boq_id', '=', rec.id)]
            )
            rec.certificate_count = Certificate.search_count(domain)

    def action_view_certificates(self):
        self.ensure_one()
        domain = (
            ['|', ('boq_id', '=', self.id), ('project_id', '=', self.project_id.id)]
            if self.project_id
            else [('boq_id', '=', self.id)]
        )
        return {
            'type': 'ir.actions.act_window',
            'name': 'المستخلصات',
            'res_model': 'construction.certificate',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                'default_boq_id': self.id,
                'default_project_id': self.project_id.id if self.project_id else False,
            },
        }
