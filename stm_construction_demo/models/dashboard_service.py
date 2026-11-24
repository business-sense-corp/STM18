# -*- coding: utf-8 -*-
from odoo import api, models


class ConstructionDashboardService(models.AbstractModel):
    _name = 'construction.dashboard.service'
    _description = 'خدمة بيانات لوحة الإدارة التنفيذية والمساعد الذكي'

    def _get_kpi_config(self):
        KpiConfig = self.env['construction.kpi.config']
        cfg = KpiConfig.search([], order='id asc', limit=1)
        if not cfg:
            cfg = KpiConfig.create({'name': 'إعدادات لوحة الإدارة والسيولة'})
        return cfg

    def _get_featured_unit_cost(self, project_id=False):
        UnitCost = self.env['construction.unit.cost']
        if project_id:
            uc = UnitCost.search([('project_id', '=', project_id)], order='is_featured desc, id desc', limit=1)
            if uc:
                return uc
        uc = UnitCost.search([('is_featured', '=', True)], order='id desc', limit=1)
        if not uc:
            uc = UnitCost.search([], order='id desc', limit=1)
        if not uc:
            uc = UnitCost.create({'name': 'بلوك إشراقات السكني — 10 وحدات', 'is_featured': True})
        return uc

    @api.model
    def get_dashboard_data(self, project_id=False):
        project_id = int(project_id) if project_id else False
        has_boq = 'construction.boq' in self.env
        has_cert = 'construction.certificate' in self.env
        has_proj_stm = 'stm_delay_days' in self.env['project.project']._fields

        Project = self.env['project.project']
        if has_proj_stm and has_boq:
            all_projects = Project.search([('stm_boq_id', '!=', False)], order='id desc')
            if not all_projects:
                all_projects = Project.search([], order='id desc')
        else:
            all_projects = Project.search([], order='id desc')
        project_options = [{'id': p.id, 'name': p.name} for p in all_projects]

        target_projects = all_projects.filtered(lambda p: p.id == project_id) if project_id else all_projects

        # --- Group 1 & 2: Projects, BOQs, Delays & Costs ---
        all_boqs = self.env['construction.boq']
        boqs = self.env['construction.boq']
        draft_boq_count = 0
        if has_boq:
            Boq = self.env['construction.boq']
            boq_domain = [('project_id', '=', project_id)] if project_id else []
            all_boqs = Boq.search(boq_domain, order='id desc')
            draft_boq_count = len(all_boqs.filtered(lambda b: b.state == 'draft'))
            boqs = all_boqs.filtered(lambda b: b.state != 'draft') or all_boqs

        delayed_list = []
        seen_proj_ids = set()
        for b in boqs:
            if b.delay_days and b.delay_days > 0:
                delayed_list.append({
                    'name': b.project_name or b.name,
                    'boq_ref': b.name,
                    'delay_days': b.delay_days,
                    'delay_reason': b.delay_reason or 'تأخير تشغيلي مسجل بالمقايسة',
                    'res_model': 'construction.boq',
                    'res_id': b.id,
                })
                if b.project_id:
                    seen_proj_ids.add(b.project_id.id)

        if has_proj_stm:
            for p in target_projects:
                if p.id not in seen_proj_ids and p.stm_delay_days and p.stm_delay_days > 0:
                    delayed_list.append({
                        'name': p.name,
                        'boq_ref': p.stm_boq_id.name if has_boq and p.stm_boq_id else p.name,
                        'delay_days': p.stm_delay_days,
                        'delay_reason': p.stm_delay_reason or 'تأخير مسجل ببطاقة المشروع',
                        'res_model': 'project.project',
                        'res_id': p.id,
                    })

        # Delayed tasks (if S1 fields exist)
        delayed_tasks = []
        if 'stm_is_delayed' in self.env['project.task']._fields:
            task_domain = [('stm_is_delayed', '=', True)]
            if project_id:
                task_domain.append(('project_id', '=', project_id))
            for t in self.env['project.task'].search(task_domain, limit=5, order='stm_delay_days desc'):
                delayed_tasks.append({
                    'name': t.name,
                    'project_name': t.project_id.name,
                    'delay_days': t.stm_delay_days,
                    'delay_reason': t.stm_delay_reason or '',
                    'res_model': 'project.task',
                    'res_id': t.id,
                })

        if boqs:
            avg_progress_actual = round(sum(boqs.mapped('progress_percent')) / len(boqs), 1)
            avg_progress_planned = 85.0
            if has_proj_stm:
                linked_projs = boqs.mapped('project_id')
                if linked_projs:
                    avg_progress_planned = round(
                        sum(linked_projs.mapped('stm_progress_planned')) / len(linked_projs), 1
                    )
        else:
            avg_progress_actual = 0.0
            avg_progress_planned = 0.0
            if has_proj_stm and target_projects:
                avg_progress_actual = round(
                    sum(target_projects.mapped('stm_progress_actual')) / len(target_projects), 1
                )
                avg_progress_planned = round(
                    sum(target_projects.mapped('stm_progress_planned')) / len(target_projects), 1
                )

        total_planned = sum(boqs.mapped('total_planned')) if boqs else 0.0
        total_actual = sum(boqs.mapped('total_actual')) if boqs else 0.0
        total_committed = sum(boqs.mapped('total_committed')) if boqs else 0.0
        total_etc = sum(boqs.mapped('total_etc')) if boqs else 0.0
        total_eac = sum(boqs.mapped('total_eac')) if boqs else 0.0
        variance = total_eac - total_planned
        variance_pct = round((variance / total_planned) * 100.0, 1) if total_planned else 0.0
        avg_cost_burn = round((total_actual / total_planned) * 100.0, 1) if total_planned else 0.0

        early_warning_projects = []
        project_chart_series = []
        for b in boqs:
            is_alert = bool(b.is_early_cost_alert or b.is_over_budget)
            if is_alert:
                early_warning_projects.append({
                    'id': b.id,
                    'name': b.project_name or b.name,
                    'boq_ref': b.name,
                    'progress_percent': round(b.progress_percent, 1),
                    'cost_burn_percent': round(b.cost_burn_percent, 1),
                    'total_planned': b.total_planned,
                    'total_actual': b.total_actual,
                    'total_eac': b.total_eac,
                    'is_early_cost_alert': b.is_early_cost_alert,
                    'is_over_budget': b.is_over_budget,
                    'currency_symbol': b.currency_id.symbol or 'ر.س',
                    'res_model': 'construction.boq',
                    'res_id': b.id,
                })
            if len(project_chart_series) < 5 and (b.total_planned > 0 or b.total_actual > 0):
                project_chart_series.append({
                    'name': b.project_name or b.name,
                    'planned': b.total_planned,
                    'actual': b.total_actual,
                    'eac': b.total_eac,
                    'progress': round(b.progress_percent, 1),
                    'cost_burn': round(b.cost_burn_percent, 1),
                    'is_alert': is_alert,
                    'res_model': 'construction.boq',
                    'res_id': b.id,
                })

        # --- Featured 10-Unit Block & KPI Config ---
        uc = self._get_featured_unit_cost(project_id=project_id)
        kpi = self._get_kpi_config()

        if not project_chart_series and uc:
            project_chart_series.append({
                'name': uc.name,
                'planned': uc.block_budget,
                'actual': uc.block_actual,
                'eac': uc.block_eac,
                'progress': 70.0,
                'cost_burn': round((uc.block_actual / uc.block_budget) * 100.0, 1) if uc.block_budget else 0.0,
                'is_alert': uc.block_variance > 0,
                'res_model': 'construction.unit.cost',
                'res_id': uc.id,
            })

        # --- Group 3: Real Estate Units, Handover & Online Bookings ---
        ProductTmpl = self.env['product.template']
        unit_domain = [('stm_is_real_estate_unit', '=', True)]
        if project_id:
            unit_domain.append(('stm_project_id', '=', project_id))
        units = ProductTmpl.search(unit_domain)

        avail_counts = {
            'available': len(units.filtered(lambda u: u.stm_unit_availability == 'available')),
            'reserved': len(units.filtered(lambda u: u.stm_unit_availability == 'reserved')),
            'sold': len(units.filtered(lambda u: u.stm_unit_availability == 'sold')),
            'total_units': len(units),
        }
        readiness_counts = {
            'under_construction': len(units.filtered(lambda u: u.stm_handover_readiness == 'under_construction')),
            'ready': len(units.filtered(lambda u: u.stm_handover_readiness == 'ready')),
            'handed_over': len(units.filtered(lambda u: u.stm_handover_readiness == 'handed_over')),
        }

        Booking = self.env['construction.online.booking']
        all_bookings = Booking.search([])
        incoming_bookings = len(all_bookings.filtered(lambda b: b.state == 'incoming'))
        under_review_bookings = len(all_bookings.filtered(lambda b: b.state == 'under_review'))
        approved_bookings = len(all_bookings.filtered(lambda b: b.state == 'approved'))

        Contract = self.env['real.estate.contract']
        contract_domain = [('state', '!=', 'cancelled')]
        if project_id:
            contract_domain.append(('stm_project_id', '=', project_id))
        contracts = Contract.search(contract_domain)

        handover_counts = {
            'pending': len(contracts.filtered(lambda c: c.stm_handover_status == 'pending')),
            'ready': len(contracts.filtered(lambda c: c.stm_handover_status == 'ready')),
            'approved': len(contracts.filtered(lambda c: c.stm_handover_status == 'approved')),
            'delivered': len(contracts.filtered(lambda c: c.stm_handover_status == 'delivered')),
        }

        # --- Group 4: Certificates & Multi-Currency Contracts ---
        cert_summary = {
            'available': has_cert,
            'vendor_count': 0,
            'vendor_total_net': 0.0,
            'vendor_pending_count': 0,
            'vendor_pending_net': 0.0,
            'customer_count': 0,
            'customer_total_net': 0.0,
            'total_retention_held': 0.0,
            'currency_symbol': 'ر.س',
        }
        pending_certs = self.env['construction.certificate'] if has_cert else False
        if has_cert:
            Cert = self.env['construction.certificate']
            cert_domain = [('state', '!=', 'rejected')]
            if project_id:
                cert_domain.append(('project_id', '=', project_id))
            certs = Cert.search(cert_domain)
            vendor_certs = certs.filtered(lambda c: c.certificate_type == 'vendor')
            customer_certs = certs.filtered(lambda c: c.certificate_type == 'customer')
            pending_certs = vendor_certs.filtered(lambda c: c.state in ('draft', 'site_engineer', 'pm_approved', 'accounting'))
            cert_summary.update({
                'vendor_count': len(vendor_certs),
                'vendor_total_net': sum(vendor_certs.mapped('net_payable_curr')),
                'vendor_pending_count': len(pending_certs),
                'vendor_pending_net': sum(pending_certs.mapped('net_payable_curr')),
                'customer_count': len(customer_certs),
                'customer_total_net': sum(customer_certs.mapped('net_payable_curr')),
                'total_retention_held': sum(certs.mapped('retention_cumul')),
                'currency_symbol': (certs[0].currency_id.symbol or 'ر.س') if certs else 'ر.س',
            })

        # Strictly group contracts by currency (NEVER mix EGP and SAR!)
        currency_buckets = {}
        all_contracts_for_currency = Contract.search([('state', '!=', 'cancelled')])
        for c in all_contracts_for_currency:
            cur = c.currency_id or self.env.company.currency_id
            key = cur.id
            if key not in currency_buckets:
                currency_buckets[key] = {
                    'currency_name': cur.name,
                    'currency_symbol': cur.symbol or cur.name,
                    'count': 0,
                    'total_cash_price': 0.0,
                }
            currency_buckets[key]['count'] += 1
            currency_buckets[key]['total_cash_price'] += c.total_cash_price or 0.0
        contracts_by_currency = list(currency_buckets.values())

        # --- Group 5: Executive Alerts ---
        alerts = []
        if early_warning_projects:
            top_ew = early_warning_projects[0]
            alerts.append({
                'key': 'cost_overrun',
                'severity': 'critical',
                'title': f"إنذار تكلفة مبكر ({len(early_warning_projects)})",
                'detail': f"{top_ew['name']}: إنجاز {top_ew['progress_percent']}% مقابل صرف {top_ew['cost_burn_percent']}%",
                'scenario_key': 'cost_overrun',
                'res_model': top_ew['res_model'],
                'res_id': top_ew['res_id'],
            })
        elif uc and uc.block_variance > 0:
            alerts.append({
                'key': 'cost_overrun',
                'severity': 'warning',
                'title': 'انحراف متوقع بالبلوك',
                'detail': f"{uc.name}: انحراف +{uc.block_variance:,.0f} {uc.currency_id.symbol or 'ر.س'}",
                'scenario_key': 'cost_overrun',
                'res_model': 'construction.unit.cost',
                'res_id': uc.id,
            })

        if delayed_list:
            top_del = delayed_list[0]
            alerts.append({
                'key': 'delay',
                'severity': 'warning',
                'title': f"مشاريع متأخرة ({len(delayed_list)})",
                'detail': f"{top_del['name']}: تأخير {top_del['delay_days']} يوم",
                'scenario_key': 'delay',
                'res_model': top_del['res_model'],
                'res_id': top_del['res_id'],
            })

        if kpi.cash_deficit_amount > 0:
            alerts.append({
                'key': 'liquidity',
                'severity': 'warning',
                'title': 'فجوة سيولة متوقعة (60 يوم)',
                'detail': f"عجز متوقع {kpi.cash_deficit_amount:,.0f} {kpi.currency_id.symbol or 'ر.س'}",
                'scenario_key': 'liquidity',
                'res_model': 'construction.kpi.config',
                'res_id': kpi.id,
            })

        if incoming_bookings > 0:
            first_bk = all_bookings.filtered(lambda b: b.state == 'incoming')[:1]
            alerts.append({
                'key': 'booking',
                'severity': 'info',
                'title': f"حجوزات موقع واردة ({incoming_bookings}) — محاكاة",
                'detail': 'بانتظار الاعتماد والتحويل لأمر بيع',
                'scenario_key': False,
                'res_model': 'construction.online.booking',
                'res_id': first_bk.id if first_bk else False,
            })

        return {
            'project_options': project_options,
            'selected_project_id': project_id or 0,
            'projects': {
                'total_count': len(target_projects),
                'boq_count': len(boqs),
                'draft_boq_count': draft_boq_count,
                'avg_progress_planned': avg_progress_planned,
                'avg_progress_actual': avg_progress_actual,
                'delayed_count': len(delayed_list),
                'delayed_list': delayed_list,
                'delayed_tasks': delayed_tasks,
            },
            'costs': {
                'has_boq': has_boq,
                'total_planned': total_planned,
                'total_actual': total_actual,
                'total_committed': total_committed,
                'total_etc': total_etc,
                'total_eac': total_eac,
                'variance': variance,
                'variance_pct': variance_pct,
                'avg_cost_burn': avg_cost_burn,
                'currency_symbol': (boqs[0].currency_id.symbol or 'ر.س') if boqs else 'ر.س',
                'early_warning_projects': early_warning_projects,
                'project_chart_series': project_chart_series,
                'materials': {
                    'config_id': kpi.id,
                    'planned': kpi.materials_planned_cost,
                    'consumed': kpi.materials_consumed_cost,
                    'waste': kpi.materials_waste_cost,
                    'waste_pct': round(kpi.materials_waste_pct, 1),
                    'currency_symbol': kpi.currency_id.symbol or 'ر.س',
                },
            },
            'real_estate': {
                'availability': avail_counts,
                'readiness': readiness_counts,
                'incoming_bookings': incoming_bookings,
                'under_review_bookings': under_review_bookings,
                'approved_bookings': approved_bookings,
                'total_bookings': len(all_bookings),
                'handover': handover_counts,
                'contracts_total_count': len(all_contracts_for_currency),
            },
            'finance': {
                'certificates': cert_summary,
                'contracts_by_currency': contracts_by_currency,
                'unit_cost': {
                    'id': uc.id,
                    'name': uc.name,
                    'project_name': uc.project_id.name if uc.project_id else 'مجمع إشراقات السكني',
                    'units_count': uc.units_count,
                    'block_budget': uc.block_budget,
                    'block_actual': uc.block_actual,
                    'block_etc': uc.block_etc,
                    'block_eac': uc.block_eac,
                    'block_variance': uc.block_variance,
                    'block_variance_pct': round(uc.block_variance_pct, 1),
                    'unit_planned_cost': uc.unit_planned_cost,
                    'unit_actual_cost': uc.unit_actual_cost,
                    'unit_expected_cost': uc.unit_expected_cost,
                    'unit_net_sale_price': uc.unit_net_sale_price,
                    'unit_cash_collected': uc.unit_cash_collected,
                    'unit_cash_collected_pct': round(uc.unit_cash_collected_pct, 1),
                    'unit_remaining_receivable': uc.unit_remaining_receivable,
                    'unit_expected_margin': uc.unit_expected_margin,
                    'unit_expected_margin_pct': round(uc.unit_expected_margin_pct, 1),
                    'accounting_note': uc.accounting_note,
                    'currency_symbol': uc.currency_id.symbol or 'ر.س',
                },
                'liquidity_sim': {
                    'id': kpi.id,
                    'cash_inflow_expected': kpi.cash_inflow_expected,
                    'cash_outflow_expected': kpi.cash_outflow_expected,
                    'cash_deficit_amount': kpi.cash_deficit_amount,
                    'overdue_installments_amount': kpi.overdue_installments_amount,
                    'escrow_balance': kpi.escrow_balance,
                    'saudization_rate': round(kpi.saudization_rate, 1),
                    'currency_symbol': kpi.currency_id.symbol or 'ر.س',
                    'is_simulated': True,
                },
            },
            'alerts': alerts,
        }

    def _route_query_to_scenario(self, scenario_key, query_text):
        if scenario_key in ('delay', 'cost_overrun', 'liquidity'):
            return scenario_key
        q = (query_text or '').strip().lower()
        if any(k in q for k in ['تأخير', 'متأخر', 'تاخير', 'توريد', 'جدول', 'delay', 'late', 'schedule']):
            return 'delay'
        if any(k in q for k in ['تكلف', 'ميزان', 'تجاوز', 'انحراف', '70', '90', 'ربح', 'هامش', 'cost', 'budget', 'overrun', 'eac', 'margin']):
            return 'cost_overrun'
        if any(k in q for k in ['سيول', 'نقد', 'عجز', 'قسط', 'أقساط', 'ضمان', 'تحصيل', 'مستخلص', 'cash', 'liquid', 'deficit', 'escrow']):
            return 'liquidity'
        return 'cost_overrun'

    @api.model
    def ask_ai_assistant(self, scenario_key=None, query_text='', project_id=False):
        data = self.get_dashboard_data(project_id=project_id)
        resolved = self._route_query_to_scenario(scenario_key, query_text)
        uc = data['finance']['unit_cost']
        kpi = data['finance']['liquidity_sim']
        sym = uc['currency_symbol'] or 'ر.س'

        if resolved == 'delay':
            delayed = data['projects']['delayed_list']
            delayed_tasks = data['projects']['delayed_tasks']
            findings = []
            sources = []
            for item in delayed[:4]:
                findings.append({
                    'label': item['name'],
                    'value': f"تأخير {item['delay_days']} يوم — السبب: {item['delay_reason']}",
                    'tone': 'warning',
                })
                sources.append({
                    'label': f"فتح {item['boq_ref'] or item['name']}",
                    'res_model': item['res_model'],
                    'res_id': item['res_id'],
                })
            for t in delayed_tasks[:2]:
                findings.append({
                    'label': f"مرحلة: {t['name']}",
                    'value': f"{t['project_name']} ({t['delay_days']} يوم) — {t['delay_reason'] or 'قيد المتابعة'}",
                    'tone': 'warning',
                })
                sources.append({
                    'label': f"فتح المهمة: {t['name']}",
                    'res_model': t['res_model'],
                    'res_id': t['res_id'],
                })

            if not findings:
                fallback_proj = self.env['project.project'].search([], order='id desc', limit=1)
                findings = [
                    {
                        'label': 'مؤشر التأخير الحالي (بيانات استرشادية)',
                        'value': 'أعمال الواجهات / توريد شحنة البورسلان — تأخير مرصود 12 يوماً عند تفعيل سيناريو السباق.',
                        'tone': 'info',
                    },
                    {
                        'label': 'متوسط الإنجاز الفعلي مقابل المخطط',
                        'value': f"{data['projects']['avg_progress_actual']}% مقابل {data['projects']['avg_progress_planned']}% مخطط",
                        'tone': 'neutral',
                    },
                ]
                if fallback_proj:
                    sources.append({
                        'label': f"استعراض المشروع: {fallback_proj.name}",
                        'res_model': 'project.project',
                        'res_id': fallback_proj.id,
                    })
                summary = 'لا توجد مشاريع متجاوزة للجدول حالياً في السجلات المفلترة، ويعرض المساعد المؤشر القياسي لمتابعة التوريدات الحرجة.'
                severity = 'info'
                severity_label = 'مراقبة الجدول'
            else:
                summary = (
                    f"تم رصد {len(delayed)} مشروع/مقايسة متأخرة بمتوسط تأخير تشغيلي ظاهر في الجدول الزمني، "
                    f"أبرزها «{delayed[0]['name']}» ({delayed[0]['delay_days']} يوماً)."
                )
                severity = 'warning'
                severity_label = 'تنبيه تأخير'

            return {
                'scenario_key': 'delay',
                'is_simulated': True,
                'badge': 'محاكاة تحليلية',
                'severity': severity,
                'severity_label': severity_label,
                'title': 'تحليل المشاريع المتأخرة والأسباب الجذرية',
                'summary': summary,
                'highlight_callout': 'التركيز الفوري على بنود التوريد الحرجة (مثل البورسلان والواجهات) يمنع ترحيل التأخير إلى مواعيد تسليم الوحدات.',
                'findings': findings,
                'sources': sources,
                'recommended_action': 'توجيه مدير المشتريات لتأكيد بديل توريد محلي أو تسريع الشحنة المتأخرة، وإعادة جدولة فرق التركيب على المسار الحرج لتعويض 6 إلى 8 أيام من التأخير.',
            }

        if resolved == 'liquidity':
            certs = data['finance']['certificates']
            findings = [
                {
                    'label': 'متحصلات متوقعة (60 يوم)',
                    'value': f"{kpi['cash_inflow_expected']:,.0f} {kpi['currency_symbol']}",
                    'tone': 'success',
                },
                {
                    'label': 'التزامات ومستخلصات متوقعة (60 يوم)',
                    'value': f"{kpi['cash_outflow_expected']:,.0f} {kpi['currency_symbol']}",
                    'tone': 'warning',
                },
                {
                    'label': 'العجز النقدي المتوقع',
                    'value': f"{kpi['cash_deficit_amount']:,.0f} {kpi['currency_symbol']}",
                    'tone': 'critical' if kpi['cash_deficit_amount'] > 0 else 'success',
                },
                {
                    'label': 'أقساط متأخرة التحصيل',
                    'value': f"{kpi['overdue_installments_amount']:,.0f} {kpi['currency_symbol']}",
                    'tone': 'warning',
                },
            ]
            if certs['available']:
                findings.append({
                    'label': 'مستخلصات مقاولين قيد الصرف',
                    'value': f"{certs['vendor_pending_count']} مستخلص ({certs['vendor_pending_net']:,.0f} {certs['currency_symbol']}) | محجوز ضمان: {certs['total_retention_held']:,.0f}",
                    'tone': 'neutral',
                })

            sources = [
                {
                    'label': 'إعدادات السيولة والضمان',
                    'res_model': 'construction.kpi.config',
                    'res_id': kpi['id'],
                },
                {
                    'label': f"بطاقة ربحية البلوك ({uc['name']})",
                    'res_model': 'construction.unit.cost',
                    'res_id': uc['id'],
                },
            ]
            if 'construction.certificate' in self.env:
                pending_cert = self.env['construction.certificate'].search(
                    [('certificate_type', '=', 'vendor'), ('state', '!=', 'rejected')],
                    order='id desc',
                    limit=1,
                )
                if pending_cert:
                    sources.append({
                        'label': f"مستخلص: {pending_cert.name}",
                        'res_model': 'construction.certificate',
                        'res_id': pending_cert.id,
                    })

            cfg = self._get_kpi_config()
            return {
                'scenario_key': 'liquidity',
                'is_simulated': True,
                'badge': 'محاكاة تحليلية',
                'severity': 'warning' if kpi['cash_deficit_amount'] > 0 else 'info',
                'severity_label': 'تنبيه سيولة',
                'title': 'موقف السيولة والتدفقات النقدية المتوقعة (60 يوماً)',
                'summary': (
                    f"توجد فجوة سيولة متوقعة بقيمة {kpi['cash_deficit_amount']:,.0f} {kpi['currency_symbol']} "
                    f"خلال الـ 60 يوماً القادمة نتيجة تزامن استحقاقات المقاولين مع تأخر تحصيل {kpi['overdue_installments_amount']:,.0f} {kpi['currency_symbol']}."
                ),
                'highlight_callout': f"تذكير محاسبي: التحصيل النقدي ({uc['unit_cash_collected']:,.0f} {sym}/وحدة) هو تدفق نقدي لا يساوي ربحاً محققاً، بينما حساب الضمان (محاكاة) يغطي {kpi['escrow_balance']:,.0f} {kpi['currency_symbol']}.",
                'findings': findings,
                'sources': sources,
                'recommended_action': cfg.ai_liquidity_recommendation or 'تسريع تحصيل الأقساط المتأخرة، إيداع شيكات PDC المستحقة، وجدولة المستخلصات غير الحرجة.',
            }

        # Default & Scenario 2: cost_overrun (70% progress vs 90% cost early warning!)
        early_list = data['costs']['early_warning_projects']
        findings = []
        sources = []

        if early_list:
            top_ew = early_list[0]
            findings.append({
                'label': f"إنذار مبكر — {top_ew['name']}",
                'value': f"الإنجاز {top_ew['progress_percent']}% مقابل صرف {top_ew['cost_burn_percent']}% (المخطط: {top_ew['total_planned']:,.0f} / المتوقع EAC: {top_ew['total_eac']:,.0f} {top_ew['currency_symbol']})",
                'tone': 'critical',
            })
            for ew in early_list[:3]:
                sources.append({
                    'label': f"فتح المقايسة: {ew['boq_ref']}",
                    'res_model': 'construction.boq',
                    'res_id': ew['res_id'],
                })
        else:
            findings.append({
                'label': 'قاعدة الإنذار المبكر النشطة',
                'value': 'رصد فجوة (نسبة الإنجاز 70% مقابل صرف 90% من الميزانية) — مثال: مخطط 100,000 مقابل متوقع 120,000 عند الإكمال.',
                'tone': 'critical',
            })
            if 'construction.boq' in self.env:
                first_boq = self.env['construction.boq'].search([], order='id desc', limit=1)
                if first_boq:
                    sources.append({
                        'label': f"فتح المقايسة: {first_boq.name}",
                        'res_model': 'construction.boq',
                        'res_id': first_boq.id,
                    })

        findings.extend([
            {
                'label': f"تكلفة البلوك المتوقعة ({uc['units_count']} وحدات)",
                'value': f"مخطط {uc['block_budget']:,.0f} → فعلي {uc['block_actual']:,.0f} + إكمال {uc['block_etc']:,.0f} = {uc['block_eac']:,.0f} {sym} (انحراف +{uc['block_variance']:,.0f})",
                'tone': 'warning' if uc['block_variance'] > 0 else 'success',
            },
            {
                'label': 'أثر التجاوز على ربحية الوحدة',
                'value': f"تكلفة متوقعة {uc['unit_expected_cost']:,.0f} مقابل بيع {uc['unit_net_sale_price']:,.0f} → هامش متوقع {uc['unit_expected_margin']:,.0f} {sym} ({uc['unit_expected_margin_pct']}%)",
                'tone': 'success',
            },
        ])
        sources.append({
            'label': f"بطاقة البلوك: {uc['name']}",
            'res_model': 'construction.unit.cost',
            'res_id': uc['id'],
        })

        return {
            'scenario_key': 'cost_overrun',
            'is_simulated': True,
            'badge': 'محاكاة تحليلية',
            'severity': 'critical',
            'severity_label': 'تحذير مبكر حرج',
            'title': 'تحليل تجاوز التكلفة والإنذار المبكر (70% إنجاز / 90% صرف)',
            'summary': (
                'رصد المساعد الذكي ارتفاعاً مبكراً في معدل استهلاك الميزانية مقارنة بنسبة الإنجاز الفعلي على الموقع، '
                f"مع انحراف متوقع في البلوك السكني بقيمة +{uc['block_variance']:,.0f} {sym} ({uc['block_variance_pct']}%)."
            ),
            'highlight_callout': 'إنذار مبكر (70% إنجاز مقابل 90% صرف): استمرار وتيرة الصرف الحالية سيرفع التكلفة النهائية للوحدة فوق 330,000 ر.س ويضغط هامش الربح المتوقع (17.5%).',
            'findings': findings,
            'sources': sources,
            'recommended_action': 'تجميد أوامر التغيير (Variation Orders) غير المعتمدة فوراً، مطابقة مستخلصات البنود الحرجة مع الكميات المنفذة فعلياً، ومراجعة تكلفة الإكمال (ETC) مع مدير المشروع قبل صرف الدفعة القادمة.',
        }
