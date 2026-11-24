# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ConstructionOnlineBooking(models.Model):
    _name = 'construction.online.booking'
    _description = 'الحجز الإلكتروني الوارد (محاكاة)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'booking_date desc, id desc'

    @api.model
    def _default_sar_currency(self):
        sar = self.env['res.currency'].search(
            [('name', '=', 'SAR'), ('active', '=', True)], limit=1
        )
        return sar or self.env.company.currency_id

    @api.model
    def _default_sync_log(self):
        now_str = fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return f'[{now_str}] [محاكاة] تم استلام طلب الحجز من الموقع الإلكتروني ومزامنته مع أودو.'

    name = fields.Char(
        string='رقم الحجز',
        required=True,
        copy=False,
        readonly=True,
        default='جديد',
    )
    source_channel = fields.Selection(
        [
            ('website', 'الموقع الإلكتروني'),
            ('portal', 'بوابة الحجز'),
            ('whatsapp', 'رابط حجز سريع'),
        ],
        string='قناة الحجز',
        default='website',
        required=True,
        tracking=True,
    )
    sync_status = fields.Selection(
        [
            ('synced_sim', 'متزامن — محاكاة'),
            ('pending', 'بانتظار المزامنة'),
        ],
        string='حالة الربط',
        default='synced_sim',
        tracking=True,
    )
    sync_log = fields.Text(
        string='سجل المزامنة (محاكاة)',
        default=_default_sync_log,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='العميل',
        required=True,
        tracking=True,
    )
    customer_phone = fields.Char(
        string='رقم الجوال',
        tracking=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='الوحدة العقارية',
        required=True,
        tracking=True,
    )
    project_categ_id = fields.Many2one(
        'product.category',
        string='المشروع / الفئة',
        related='product_id.categ_id',
        store=True,
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
    deposit_amount = fields.Monetary(
        string='مبلغ العربون',
        currency_field='currency_id',
        default=25000.0,
        tracking=True,
    )
    booking_date = fields.Datetime(
        string='تاريخ الحجز',
        default=fields.Datetime.now,
        required=True,
    )
    state = fields.Selection(
        [
            ('incoming', 'وارد من الموقع'),
            ('under_review', 'قيد المراجعة'),
            ('approved', 'معتمد'),
            ('rejected', 'مرفوض'),
        ],
        string='الحالة',
        default='incoming',
        required=True,
        tracking=True,
    )
    rejection_reason = fields.Text(
        string='سبب الرفض',
        tracking=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='أمر البيع المرتبط',
        readonly=True,
        copy=False,
    )
    notes = fields.Text(string='ملاحظات')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == 'جديد':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('construction.online.booking')
                    or 'WEB-BK/2026/001'
                )
        return super().create(vals_list)

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id and not self.customer_phone:
            self.customer_phone = self.partner_id.phone or self.partner_id.mobile

    def _append_sync_log(self, line_text):
        now_str = fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        entry = f'[{now_str}] {line_text}'
        for rec in self:
            rec.sync_log = f'{rec.sync_log}\n{entry}' if rec.sync_log else entry

    def action_start_review(self):
        for rec in self:
            if rec.state != 'incoming':
                continue
            rec.state = 'under_review'
            rec._append_sync_log('[محاكاة] تم نقل الطلب إلى قيد المراجعة من قبل فريق المبيعات.')

    def action_approve_create_sale(self):
        SaleOrder = self.env['sale.order']
        Pricelist = self.env['product.pricelist']
        for rec in self:
            if rec.state not in ('incoming', 'under_review'):
                raise UserError(_('يمكن اعتماد الطلبات الواردة أو قيد المراجعة فقط.'))
            if rec.sale_order_id:
                raise UserError(_('تم إنشاء أمر بيع مسبقاً لهذا الحجز.'))

            tmpl = rec.product_id.product_tmpl_id
            tmpl.write({
                'stm_is_real_estate_unit': True,
                'stm_unit_availability': 'reserved',
            })

            unit_price = (
                tmpl.total_cash_price
                or rec.product_id.lst_price
                or rec.deposit_amount
                or 0.0
            )
            pricelist = Pricelist.search(
                [
                    ('currency_id', '=', rec.currency_id.id),
                    ('company_id', 'in', [rec.company_id.id, False]),
                ],
                limit=1,
            )
            so_vals = {
                'partner_id': rec.partner_id.id,
                'company_id': rec.company_id.id,
                'origin': rec.name,
                'order_line': [
                    (
                        0,
                        0,
                        {
                            'product_id': rec.product_id.id,
                            'name': f'حجز وحدة عقارية: {rec.product_id.display_name} (مرجع {rec.name})',
                            'product_uom_qty': 1.0,
                            'price_unit': unit_price,
                        },
                    )
                ],
            }
            if pricelist:
                so_vals['pricelist_id'] = pricelist.id

            sale_order = SaleOrder.create(so_vals)
            rec.write({
                'sale_order_id': sale_order.id,
                'state': 'approved',
                'sync_status': 'synced_sim',
            })
            rec._append_sync_log(
                f'[محاكاة] تم تحديث حالة الوحدة بالموقع الإلكتروني إلى: محجوز، وإنشاء مسودة أمر بيع ({sale_order.name}).'
            )
            rec.message_post(
                body=_(
                    'تم اعتماد الحجز الإلكتروني (محاكاة)، وتحديث حالة الوحدة إلى محجوز، وإنشاء مسودة أمر البيع: %s.'
                )
                % sale_order.name
            )
        return self.action_view_sale_order() if len(self) == 1 else True

    def action_reject(self):
        for rec in self:
            if not rec.rejection_reason:
                raise UserError(_('يرجى كتابة سبب رفض الحجز قبل المتابعة.'))
            tmpl = rec.product_id.product_tmpl_id
            if tmpl.stm_unit_availability == 'reserved':
                tmpl.stm_unit_availability = 'available'
            rec.write({
                'state': 'rejected',
                'sync_status': 'synced_sim',
            })
            rec._append_sync_log(
                f'[محاكاة] تم رفض الحجز ({rec.rejection_reason}) وتحرير حالة الوحدة بالموقع الإلكتروني إلى: متاح للبيع.'
            )

    def action_reset_incoming(self):
        for rec in self:
            if rec.state == 'rejected':
                rec.state = 'incoming'
                rec._append_sync_log('[محاكاة] تمت إعادة الحجز إلى حالة وارد من الموقع.')

    def action_view_sale_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'أمر البيع المرتبط',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
        }
