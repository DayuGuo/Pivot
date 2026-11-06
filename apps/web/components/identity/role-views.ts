// Presentation only. All reads, work items and allowed actions come from backend policy.
export const roleViews: Record<string, { title: string; tasks: string; empty: string; prompt: string }> = {
  editor: { title: "待我处理的稿件", tasks: "编辑待办", empty: "还没有分派给你的稿件。", prompt: "查看我的编辑待办，并说明下一步需要核对什么。" },
  reviewer: { title: "我的审稿邀请", tasks: "审稿待办", empty: "目前没有发给你的审稿邀请。", prompt: "查看我的审稿邀请和待交报告，告诉我接下来需要做什么。" },
  chief_editor: { title: "期刊稿件", tasks: "主编待办", empty: "目前没有已提交的期刊稿件。", prompt: "整理待我分派和决定的稿件，指出需要我确认的事项。" },
  author: { title: "我的投稿", tasks: "作者待办", empty: "还没有投稿。可以从左侧新建投稿，或在对话中整理稿件信息。", prompt: "帮我梳理投稿信息，以及下一步需要我补充的材料。" },
  production_editor: { title: "我的制作任务", tasks: "制作待办", empty: "还没有分派给你的制作任务。", prompt: "查看我的校样和制作待办，说明下一步需要核对什么。" },
};
