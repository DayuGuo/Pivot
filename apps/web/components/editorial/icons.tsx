import type { CSSProperties } from "react";
export default function Glyph({name,size=18,style}:{name:string;size?:number;style?:CSSProperties}) {
 const paths:Record<string,React.ReactNode>={
  inbox:<><path d="M4 4h16v15H4z"/><path d="M4 13h5l2 3h2l2-3h5"/></>,
  file:<><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h4M9 12h6M9 16h6"/></>,
  people:<><circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6M18 15a5 5 0 0 1 3 5"/></>,
  check:<path d="m5 12 4 4L19 6"/>,
  search:<><circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/></>,
  arrow:<path d="m9 5 7 7-7 7M4 12h12"/>,
  back:<path d="m12 5-7 7 7 7M5 12h15"/>,
  spark:<><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/></>,
  close:<path d="m6 6 12 12M6 18 18 6"/>,
  clock:<><circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/></>,
  theme:<><circle cx="12" cy="12" r="8"/><path d="M12 4v16"/></>,
  settings:<><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="2"/><circle cx="15" cy="17" r="2"/></>,
  layers:<><path d="m3 8 9-5 9 5-9 5zM3 12l9 5 9-5M3 16l9 5 9-5"/></>,
 };
 return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style}>{paths[name]||paths.file}</svg>;
}
