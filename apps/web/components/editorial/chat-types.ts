import type {Anchor,View} from "./types";
export type ChatScope="case"|"queue"|"journal";
export type ChatContext={scope:ChatScope;case_id:string;version:string;view:View;stage:string;query:string;today_only:boolean};
export type ChatReference={label:string;case_id:string;anchor?:Anchor};
export type ChatAction={type:"navigate";view:View;case_id:string;prepare?:"invitation"|"decision"}|{type:"filter";stage:string;today_only:boolean;query:string};
export type ChatMessage={id:string;role:"user"|"assistant";content:string;created_at:string;context:ChatContext;references:ChatReference[];action?:ChatAction|null};
export type ChatTurn={request_id:string;messages:ChatMessage[];state_changed:boolean;provider:"mock"};
export type ChatHistory={messages:ChatMessage[];provider:"mock"};
