export type Author = { name: string; email: string; affiliation: string; orcid: string };
export type Paragraph = { id: string; heading: string; text: string };
export type Manuscript = {
  id: string; title: string; short: string; stage: string; task: string;
  due: string; authors: Author[]; abstract: string; paragraphs: Paragraph[];
};
export type Message = { id: string; role: "user" | "assistant"; text: string; sources?: string[]; evidence?: Record<string, string> };
export type DemoState = { version: 1; manuscripts: Manuscript[]; threads: Record<string, Message[]>; drafts: Record<string, string>; selected: string };

export const STORAGE_KEY = "publishing-os-public-demo-v1";
export function isDemoState(value: unknown): value is DemoState {
  const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
  const strings = (v: Record<string, unknown>, keys: string[]) => keys.every(k => typeof v[k] === "string");
  if (!object(value) || value.version !== 1 || typeof value.selected !== "string" || !Array.isArray(value.manuscripts) || !value.manuscripts.length || value.manuscripts.length > 100 || !object(value.threads) || !object(value.drafts)) return false;
  return value.manuscripts.every(m => object(m) && strings(m, ["id","title","short","stage","task","due","abstract"]) && Array.isArray(m.paragraphs) && m.paragraphs.every(p => object(p) && strings(p, ["id","heading","text"])) && Array.isArray(m.authors) && m.authors.every(a => object(a) && strings(a, ["name","email","affiliation","orcid"])))
    && Object.values(value.threads).every(list => Array.isArray(list) && list.every(m => object(m) && strings(m, ["id","text"]) && (m.role === "user" || m.role === "assistant") && (m.sources === undefined || Array.isArray(m.sources) && m.sources.every(s => typeof s === "string")) && (m.evidence === undefined || object(m.evidence) && Object.values(m.evidence).every(s => typeof s === "string"))))
    && Object.values(value.drafts).every(v => typeof v === "string");
}
export const REFERENCE = {
  title: "The FAIR Guiding Principles for scientific data management and stewardship",
  authors: "Wilkinson et al. (2016)", doi: "10.1038/sdata.2016.18",
  url: "https://www.nature.com/articles/sdata201618",
  record: "https://api.crossref.org/works/10.1038/sdata.2016.18",
};
export function hasReference(manuscript: Manuscript): boolean {
  return manuscript.paragraphs.some(p => p.id === "references" && p.text.includes(REFERENCE.doi));
}
export function dateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;
}
export function initialState(): DemoState {
  const due = (offset: number) => { const day = new Date(); day.setDate(day.getDate()+offset); return dateKey(day); };
  const manuscripts: Manuscript[] = [
    { id: "POS-2026-0012", short: "开放科学与数据可复现性", title: "开放科学实践与研究数据可复现性：一项多中心方法研究", stage: "编辑初筛", task: "核对方法与作者资料", due: due(0),
      authors: [{ name: "周言", email: "zhou@example.test", affiliation: "示例大学 · 信息学院", orcid: "" }, { name: "陈序", email: "chen@example.test", affiliation: "示例研究所", orcid: "" }],
      abstract: "本合成研究比较开放数据规范对研究可复现性的影响。在三个虚构研究中心的128项模拟任务中，记录数据整理、代码共享及结果复现情况，探索透明报告与复现结果之间的关系。",
      paragraphs: [
        { id: "abstract", heading: "摘要", text: "本合成研究比较开放数据规范对研究可复现性的影响。在三个虚构研究中心的128项模拟任务中，记录数据整理、代码共享及结果复现情况，探索透明报告与复现结果之间的关系。" },
        { id: "methods", heading: "方法", text: "本研究在三个虚构中心构建128项模拟任务，按是否提供结构化元数据划分两组。两位研究人员独立尝试复现分析结果；发生分歧时共同复核。现有材料尚未列出任务纳入与排除标准，也未报告数据划分的随机种子。" },
        { id: "results", heading: "结果", text: "提供结构化元数据的64项任务中有51项完成复现，另一组64项中有38项完成复现。此处数据均为演示构造，不能作为科学证据，也不能从组间差异推断因果关系。" },
        { id: "availability", heading: "数据与声明", text: "本文是 Publishing OS 的原创合成稿件。未上传研究数据、分析代码或伦理审批材料；作者利益冲突声明和贡献信息待补充。所有作者、机构与邮箱均为虚构示例。" },
        { id: "references", heading: "参考文献", text: "Wilkinson, M. D. et al. The FAIR Guiding Principles for scientific data management and stewardship. Scientific Data 3, 160018 (2016). DOI: 10.1038/sdata.2016.18。该公开文献是参考资料，并非上述合成研究的验证。" },
      ] },
    { id: "POS-2026-0018", short: "城市热岛与绿色空间", title: "城市绿色空间对夏季热环境的影响：一项模拟观察研究", stage: "寻找审稿人", task: "准备审稿邀请草稿", due: due(1), authors: [{ name: "林清", email: "lin@example.test", affiliation: "示例大学 · 环境学院", orcid: "" }], abstract: "通过虚构城市的模拟观测展示稿件审阅流程，不报告真实研究结论。", paragraphs: [{ id: "abstract", heading: "摘要", text: "通过虚构城市的模拟观测展示稿件审阅流程，不报告真实研究结论。" }, { id: "methods", heading: "方法", text: "在20个合成观测点比较模拟温度。尚需补充采样时段和混杂因素说明。" }, { id: "availability", heading: "材料说明", text: "这是原创演示资料，没有真实研究参与者。尚未提供数据文件、作者ORCID或参考文献。" }] },
    { id: "POS-2026-0021", short: "科学传播中的视觉叙事", title: "科学传播中的视觉叙事与公众理解：模拟实验", stage: "作者修回", task: "跟进修回材料", due: due(3), authors: [{ name: "许禾", email: "xu@example.test", affiliation: "示例大学 · 传播学院", orcid: "" }], abstract: "用合成材料探索科学传播视觉叙事的产品演示案例。", paragraphs: [{ id: "abstract", heading: "摘要", text: "用合成材料探索科学传播视觉叙事的产品演示案例。" }, { id: "methods", heading: "方法", text: "所有参与者和测量结果均为合成示例，目前等待作者补充研究设计说明。" }] },
  ];
  return { version: 1, manuscripts, threads: {}, drafts: {}, selected: manuscripts[0].id };
}

export function welcome(manuscript?: Manuscript): Message {
  return { id: "welcome", role: "assistant", text: manuscript
    ? `我已打开《${manuscript.title}》。目前在${manuscript.stage}，你的待办是“${manuscript.task}”。\n\n可以从方法、作者资料或参考文献开始。回答会指向右侧的原文依据；缺少的信息会单独列出。`
    : "今天先处理编辑初筛，再准备明天的审稿邀请。你可以在这里查看全刊的工作，也可以打开一篇稿件，围绕它持续讨论。\n\n这是产品交互演示。试着问我：今天有哪些工作？", sources: manuscript ? ["abstract"] : undefined, evidence: manuscript ? Object.fromEntries(manuscript.paragraphs.map(p => [p.id, p.text])) : undefined };
}

export function answer(text: string, manuscript: Manuscript | undefined, all: Manuscript[]): Omit<Message, "id"> {
  if (/发送|发邮件|录用|拒稿|撤稿|正式发表|直接批准/.test(text)) return { role: "assistant", text: "这一步必须交由有权限的负责人核对并确认。对话不能发送邮件、批准或作出正式编辑决定。\n\n本演示没有邮件或业务接口，刚才的请求没有改变稿件状态，也没有产生外发操作。" };
  if (!manuscript) return { role: "assistant", text: `目前有 ${all.length} 篇演示稿件待跟进：\n\n${all.map(m => `${m.id}｜${m.stage}\n${m.task}，截止 ${m.due}。`).join("\n\n")}\n\n从左侧选择稿件，就能查看材料并在对应会话中继续审阅。` };
  if (/作者|ORCID|orcid|元数据|资料|缺/.test(text)) {
    const missing = manuscript.authors.filter(a => !a.orcid);
    return { role: "assistant", text: `本稿目前登记 ${manuscript.authors.length} 位作者：${manuscript.authors.map(a => a.name).join("、")}。\n\n${missing.length ? `${missing.map(a => a.name).join("、")}未提供 ORCID。` : "已填写的 ORCID 仅为手工录入，尚未通过本人授权认证。"}机构和邮箱为合成示例，不能据此确认真实身份。\n\n请在右侧“作者”补充资料，再由负责人核对。AI不会代替作者作伦理、原创性或利益冲突声明。`, sources: manuscript.paragraphs.some(p => p.id === "availability") ? ["availability"] : ["abstract"] };
  }
  if (/文献|引用|链接|FAIR|DOI|doi|来源/.test(text)) return hasReference(manuscript) ? { role: "assistant", text: `参考文献中列出的 FAIR 原则论文确实存在：\n\n${REFERENCE.title}\n${REFERENCE.authors}，DOI ${REFERENCE.doi}。\n\n右侧“证据”提供出版社原文与 Crossref 元数据记录。该文支持开放数据原则的背景说明，不能验证本稿的模拟结果。Crossref记录在制作演示时核对；出版社页面可能要求浏览器验证，并非本次对话实时检索。`, sources: ["references", "external"] } : { role: "assistant", text: "这篇演示稿尚未录入本演示可核对的参考文献。我不能补造论文或核验链接。先补充原文和参考文献；新文献的实时核验尚未接通。", sources: ["abstract"] };
  if (/方法|审阅|问题|检查|质量/.test(text)) {
    const methods = manuscript.paragraphs.find(p => p.id === "methods");
    return { role: "assistant", text: `先核对本版的方法材料：\n\n“${methods?.text || manuscript.abstract}”\n\n${methods?.text.includes("尚未列出任务纳入与排除标准，也未报告数据划分的随机种子") ? "目前可见两处缺项：任务纳入与排除标准、数据划分的随机种子。建议请作者补充；现有模拟结果不能支持因果结论。" : "上方为当前材料的实际摘录。本演示没有模型分析能力，不会把新录入的文本自动判为合格或不合格；请由编辑核对完整性与质量。"}\n\n这是基于演示材料的预设审阅提示，是否送审仍由责任编辑判断。`, sources: [methods ? "methods" : "abstract"] };
  }
  if (/概括|总结|状态|进展|下一步|介绍/.test(text)) return { role: "assistant", text: `《${manuscript.title}》\n\n${manuscript.abstract}\n\n当前步骤：${manuscript.stage}。\n你的下一项工作：${manuscript.task}，截止 ${manuscript.due}。\n\n以上是当前浏览器保存的演示资料，不代表真实业务进展。`, sources: ["abstract"] };
  return { role: "assistant", text: "本演示使用预设模拟问答，还没有连接通用模型。你可以问“概括这篇稿件”“检查方法”“核对作者信息”或“查看参考文献”，体验材料与对话如何关联。\n\n右侧资料可以实际编辑并保存在当前浏览器。" };
}
