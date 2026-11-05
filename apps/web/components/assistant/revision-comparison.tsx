"use client";
import styles from './revision-comparison.module.css';

export type RevisionComparison = {
  schema: string;
  provider: string;
  base_version_id: string;
  revised_version_id: string;
  point_count: number;
  all_points_included: boolean;
  rereview_required: boolean;
  coverage: Record<string, { read_characters: number; total_characters: number; complete: boolean }>;
  rows: {
    point_id: string;
    status: string;
    reason: string;
    point: { text: string; label: string; complete: boolean };
    citations: { kind: string; version_no: number; quote: string; line_start: number; line_end: number; sha256: string }[];
  }[];
};
const labels: Record<string, string> = {
  resolved: '修改有证据', explained: '解释但未改动', partial: '部分回应',
  not_addressed: '尚未回应', uncertain: '证据不足，待核对', not_applicable: '非修改要求，供核对',
};
const material: Record<string, string> = { response: '作者回复', revised: '修订稿', base: '原稿' };

export default function RevisionComparisonPanel({ report }: { report: RevisionComparison }) {
  if (report.schema !== 'revision-comparison.v1') return null;
  const complete = report.all_points_included && Object.values(report.coverage).every(c => c.complete);
  return <section className={styles.panel} aria-label="修回逐项对照">
    <p>{report.provider === 'mock' ? 'Mock模拟，未作语义判断' : 'AI辅助判断，仍须负责人核对'} · 本次 {report.rows.length}/{report.point_count} 项意见{complete ? '' : ' · 材料或意见未完整覆盖'}</p>
    {report.rereview_required && <p>本次大修仍需按正式流程重新送审。</p>}
    {report.rows.map(row => <section key={row.point_id} className={styles.point}>
      <h3>{row.point_id} · {labels[row.status] || '待核对'}</h3>
      <p>{row.point.label}</p>
      <blockquote>{row.point.text}</blockquote>
      {!row.point.complete && <p>本项原意见仅显示前段，不能据此认定已全部回应。</p>}
      <p>{row.reason}</p>
      <details>
        <summary>核对原文依据（{row.citations.length}）</summary>
        {row.citations.length ? row.citations.map((c, i) => <div key={i}>
          <p>{material[c.kind]} · v{c.version_no} · 第 {c.line_start}{c.line_end !== c.line_start ? `–${c.line_end}` : ''} 行</p>
          <blockquote>{c.quote}</blockquote><code>{c.sha256}</code>
        </div>) : <p>尚无可验证引文，不能认定修改完成。</p>}
      </details>
    </section>)}
    <p>此对照不确认修回、不发邮件、不作录用或退稿决定。</p>
  </section>;
}
