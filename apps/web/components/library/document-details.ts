export function documentLocation(kind: string, number: number) { return kind === "pdf_page" ? `PDF 第 ${number} 页` : `Word 第 ${number} 段`; }
export function documentWarning(value: string) {
  const messages: Record<string, string> = {
    pdf_initial_page_destination_ignored: "已忽略 PDF 的默认打开页设置，没有执行任何动作。",
    docx_list_markers_not_rendered: "已提取列表正文，自动项目符号和列表编号未重建，请对照 Word 核对层级与编号。",
    docx_pagination_not_rendered: "原 Word 页码字段没有已保存的显示值，未生成页码；正文仍按提取段定位。",
    docx_cached_fields_not_updated: "引文和页码保留 Word 中已保存的显示文字，未执行或更新字段；请核对是否过期。",
    pdf_text_reading_order_requires_review: "PDF 的阅读顺序需要对照原稿核对。",
    figures_images_and_equations_not_interpreted: "图片、图示和公式未作语义识别，请对照原稿检查。",
    docx_paragraph_numbers_are_extraction_order_not_page_numbers: "Word 按提取顺序编号段落，段落号不是页码。",
    tables_notes_headers_footers_are_linearized: "表格、注释、页眉和页脚已转为顺序文本，请核对上下文。",
    external_hyperlink_targets_ignored: "已保留超链接文字，未访问链接目标。",
    docx_images_and_figures_not_interpreted: "Word 中的图片、图示未作语义识别。",
  };
  return messages[value] ?? (/^[a-z0-9_]+$/i.test(value) ? "还有提取提示，请对照原稿人工核对相关内容。" : value);
}
