"""报告渲染器：HTML（单文件内联、断网可开）与 JSON（机读）同源双轨。

两个渲染器都只消费 ``sections.build_sections`` 的结构化章节——
"两格式内容一致"是**结构性质**（同一渲染源），非人工比对。

确定性（同输入 → 同字节）：
- 无时间戳、无随机 id、无字典序依赖（全部显式排序或取自产物固定序）；
- 数值格式固定（金额分 → "%d.%02d"）；
- HTML 转义经 html.escape 固定规则；JSON 用固定缩进 + ensure_ascii=False。
"""

import json
from html import escape

from .sections import SCHEMA_VERSION

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>bill-reconciler 对账报告</title>
<style>
body {{ font-family: sans-serif; margin: 2em; color: #222; }}
h1 {{ font-size: 1.5em; }} h2 {{ font-size: 1.2em; margin-top: 1.5em; }}
table {{ border-collapse: collapse; margin: 0.5em 0; }}
td, th {{ border: 1px solid #999; padding: 2px 8px; font-size: 90%; }}
ul {{ margin: 0.3em 0; }} .note {{ color: #666; font-size: 85%; }}
code {{ background: #f4f4f4; padding: 0 4px; }}
</style>
</head>
<body>
<h1>多平台账单『真实支出』对账报告</h1>
{body}
<p class="note">本报告由 bill-reconciler 离线生成（单一渲染源：sections.py；断网可开，无外链）。</p>
</body>
</html>
"""


def render_html(report):
    """结构化报告 → 单文件 HTML 字节串（无外链、无脚本、确定性）。"""
    s = report["sections"]
    parts = []

    ov = s["overview"]
    parts.append("<h2>%s</h2>" % escape(ov["title"]))
    parts.append("<p>记录 %d 条；ruleset v%s；参数 digest <code>%s</code></p>" % (
        ov["records_total"], escape(str(ov["ruleset_version"])),
        escape(str(ov["params_digest"]))))
    parts.append("<table><tr><th>文件</th><th>平台</th><th>编码</th>"
                 "<th>ok</th><th>invalid</th><th>unknown</th></tr>")
    for f in ov["files"]:
        parts.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%d</td>"
                     "<td>%d</td><td>%d</td></tr>" % (
                         escape(f["file"]), escape(f["platform"]),
                         escape(f["encoding"]), f["rows_ok"],
                         f["rows_invalid"], f["rows_unknown"]))
    parts.append("</table>")
    parts.append("<p>平台行数：%s；时间范围：%s ~ %s；流水线段：%s</p>" % (
        escape(_pairs(ov["rows_by_platform"])),
        escape(str(ov["time_range"]["from"])),
        escape(str(ov["time_range"]["to"])),
        escape(" → ".join(ov["pipeline_stages"]))))

    rs = s["real_spend"]
    parts.append("<h2>%s</h2>" % escape(rs["title"]))
    parts.append("<p>%s</p>" % escape(rs["basis"]))
    parts.append("<p>净支出 <strong>%s</strong> 元；净收入 %s 元；"
                 "排除重复 %d 条</p>" % (
                     escape(rs["net_expense"]), escape(rs["net_income"]),
                     len(rs["excluded_duplicates"])))

    dd = s["dedup"]
    parts.append("<h2>%s</h2>" % escape(dd["title"]))
    parts.append("<p class=\"note\">窗口参数：%s</p>" % escape(str(dd["params"])))
    parts.append("<table><tr><th>簇</th><th>判定</th><th>方向</th>"
                 "<th>对手方</th><th>金额</th><th>平台</th><th>成员</th>"
                 "<th>代表笔</th></tr>")
    for c in dd["clusters"]:
        parts.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                     "<td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                         escape(c["cluster_id"]), escape(c["verdict"]),
                         escape(c["direction"]), escape(c["counterparty"]),
                         escape(_amount(c["amount"])),
                         escape("、".join(c["platforms"])),
                         escape("、".join(c["members"])),
                         escape(str(c["representative"]))))
    parts.append("</table>")
    parts.append("<p>跨平台重复 %d 簇；同平台候选（不合并，待人工复核）%d 簇</p>" % (
        len(dd["duplicate_cross_platform"]),
        len(dd["candidate_same_platform"])))

    se = s["semantic"]
    parts.append("<h2>%s</h2>" % escape(se["title"]))
    parts.append("<p>%s</p>" % escape(_pairs(se["distribution"])))
    parts.append("<p class=\"note\">%s；未知 %d 行、合计 %s 元"
                 "（主口径未计入；若全部计入支出上限为 %s 元）</p>" % (
                     escape(se["note"]), se["unknown_count"],
                     escape(se["unknown_amount_total"]),
                     escape(se["unknown_upper_bound"])))

    sb = s["subscription"]
    parts.append("<h2>%s</h2>" % escape(sb["title"]))
    for sub in sb["subscriptions"]:
        parts.append("<p><strong>%s</strong> %s（%s，%d 期，%s ~ %s）成员：%s</p>" % (
            escape(sub["subscription_id"]), escape(sub["merchant"]),
            escape(sub["period_id"]), sub["repeats"],
            escape(sub["first_time"]), escape(sub["last_time"]),
            escape("、".join(sub["entries"]))))
        for change in sub["price_changes"]:
            parts.append("<p class=\"note\">涨价：%s 由 %s 元 → %s 元"
                         "（%s）</p>" % (
                             escape(change["entry"]),
                             escape(change["from_amount"]),
                             escape(change["to_amount"]),
                             escape(change["to_time"])))
        for gap in sub["gaps"]:
            parts.append("<p class=\"note\">中断：漏 %d 期，%s 之后于 %s 续接</p>" % (
                gap["missed_intervals"], escape(gap["after_entry"]),
                escape(gap["resumed_entry"])))
    if not sb["subscriptions"]:
        parts.append("<p>未识别到周期性订阅。</p>")
    parts.append("<p class=\"note\">%s</p>" % escape(sb["note"]))

    iss = s["issues"]
    parts.append("<h2>%s</h2>" % escape(iss["title"]))
    if iss["row_issues"]:
        parts.append("<ul>")
        for i in iss["row_issues"]:
            parts.append("<li>[%s] %s：%s</li>" % (
                escape(i["kind"]), escape(str(i["row_id"])),
                escape(i["detail"])))
        parts.append("</ul>")
    else:
        parts.append("<p>无行级问题。</p>")
    for f in iss["file_issues"]:
        parts.append("<p>文件级失败 [%s] %s：%s</p>" % (
            escape(f["code"]), escape(f["file"]), escape(f["detail"])))

    pa = s["params"]
    parts.append("<h2>%s</h2>" % escape(pa["title"]))
    parts.append("<table><tr><th>参数</th><th>值</th><th>来源</th></tr>")
    for entry in pa["entries"]:
        parts.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            escape(entry["param"]), escape(_json_value(entry["value"])),
            escape(entry["source"])))
    parts.append("</table>")

    cl = s["closing"]
    parts.append("<h2>%s</h2>" % escape(cl["title"]))
    parts.append("<ul>")
    for line in cl["privacy"]:
        parts.append("<li>%s</li>" % escape(line))
    for line in cl["disclaimer"]:
        parts.append("<li>%s</li>" % escape(line))
    parts.append("</ul>")

    return _HTML_TEMPLATE.format(body="\n".join(parts))


def render_json_bytes(report):
    """结构化报告 → 机读 JSON 字节串（固定缩进，确定性）。"""
    payload = dict(report)
    payload["_render_note"] = "机读双轨：与 report.html 同一渲染源（sections.py）"
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    return (text + "\n").encode("utf-8")


def write_report(report, html_path, json_path):
    """双轨落盘（字节写出，Windows 下固定 LF 由字节串保证）。"""
    html_text = render_html(report).replace("\r\n", "\n")
    _write_bytes(html_path, html_text.encode("utf-8"))
    _write_bytes(json_path, render_json_bytes(report))


def _write_bytes(path, data):
    from pathlib import Path

    out = Path(path)
    if out.parent and not out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)


def _pairs(mapping):
    return "；".join("%s=%s" % (k, v) for k, v in sorted(mapping.items()))


def _amount(value):
    return str(value) if value is not None else "-"


def _json_value(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


__all__ = ["SCHEMA_VERSION", "render_html", "render_json_bytes", "write_report"]
