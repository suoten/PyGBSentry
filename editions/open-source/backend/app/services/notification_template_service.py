import json
from typing import Any
from jinja2 import Template

TEMPLATES: dict[str, dict[str, str]] = {
    "sla_breach_alert": {
        "title": "SLA违约告警",
        "text": "时间: {{ timestamp }}\n数量: {{ count }}\n连续周期: {{ consecutive_cycles }}\nTop告警: {% for item in items[:5] %}\n- {{ item.alarm_id }} 设备={{ item.device_id }} 优先级={{ item.priority }} 级别={{ item.escalation_level }}{% endfor %}",
        "email_subject": "PyGBSentry SLA Breach Alert",
        "email_body": "SLA breach detected at {{ timestamp }}\ncount={{ count }}\nconsecutive_cycles={{ consecutive_cycles }}",
    },
    "daily_health_report": {
        "title": "巡检日报",
        "text": "时间: {{ timestamp }}\n设备总数: {{ total_devices }}\n高风险: {{ high_risk }}\n中风险: {{ medium_risk }}\n低风险: {{ low_risk }}\nTop设备: {% for item in top_risky[:8] %}\n- {{ item.device_id }} 风险={{ item.risk_level }} 失败率={{ item.failure_rate }}{% endfor %}",
        "email_subject": "PyGBSentry Daily Health Report",
        "email_body": "Daily Health Report {{ timestamp }}\ntotal_devices={{ total_devices }}\nhigh_risk={{ high_risk }}\nmedium_risk={{ medium_risk }}\nlow_risk={{ low_risk }}\n{% for item in top_risky[:10] %}- {{ item.device_id }} risk={{ item.risk_level }} failure_rate={{ item.failure_rate }} consecutive_failures={{ item.consecutive_failures }}\n{% endfor %}",
    },
    "subscription_expiry_reminder": {
        "title": "订阅到期提醒",
        "text": "租户: {{ tenant_id }}\n套餐: {{ plan_code }}\n类型: {{ reminder_type }}\n订阅到期: {{ ends_at }}",
        "email_subject": "PyGBSentry Subscription Reminder",
        "email_body": "tenant={{ tenant_id }}\nplan={{ plan_code }}\nreminder_type={{ reminder_type }}\nends_at={{ ends_at }}",
    },
}

def render_template(event: str, channel: str, context: dict[str, Any]) -> str:
    event_tpl = TEMPLATES.get(event, {})
    template_text = event_tpl.get(channel) or "{{ data }}"
    try:
        return Template(template_text).render(**context, data=json.dumps(context, ensure_ascii=False))
    except Exception:
        return json.dumps(context, ensure_ascii=False)

def render_webhook_payload(event: str, platform: str, context: dict[str, Any]) -> dict[str, Any]:
    title = render_template(event, "title", context)
    text = render_template(event, "text", context)
    if platform == "feishu":
        return {"msg_type": "text", "content": {"text": f"{title}\n{text}"}}
    if platform == "wechat":
        return {"msgtype": "text", "text": {"content": f"{title}\n{text}"}}
    data = dict(context)
    data["title"] = title
    data["text"] = text
    return data

def render_email(event: str, context: dict[str, Any]) -> tuple[str, str]:
    subject = render_template(event, "email_subject", context)
    body = render_template(event, "email_body", context)
    return subject, body
