// Public synthetic DOCX fixture. Install docx only in a temporary fixture tool folder.
const fs = require('node:fs');
const {Document,Packer,Paragraph,TextRun,ExternalHyperlink,Table,TableRow,TableCell,WidthType}=require(process.env.DOCX_FIXTURE_MODULE || '/tmp/pivot-document-fixtures/node_modules/docx');
const lines=[
 'Title: Synthetic Editorial Review Manuscript',
 'Authors: Synthetic Author Alpha; Synthetic Author Beta',
 'Author 1: Synthetic Author Alpha',
 'Email 1: alpha@synthetic.test',
 'ORCID 1: 0000-0002-1825-0097',
 'Affiliation 1: Synthetic Research Institute',
 'Corresponding author: Synthetic Author Alpha',
 'Author 2: Synthetic Author Beta',
 'Email 2: beta@synthetic.test',
 'ORCID 2: 0000-0001-5109-3700',
 'Affiliation 2: Synthetic Publishing Laboratory',
 'Abstract: This entirely synthetic manuscript validates full text extraction, author metadata candidates, review gates and immutable source locations.',
 'Keywords: synthetic; metadata; version evidence',
 'Methods',
 'The sample contains 24 synthetic records. This is a single-arm observation.',
 'No control group is included. No real participants or confidential data exist.',
 '中文合成正文：作者、机构和数据均用于本地自动化测试，不属于真实稿件。',
 'Reference DOI: 10.1371/journal.pmed.0020124'
];
const cell=text=>new TableCell({width:{size:4500,type:WidthType.DXA},children:[new Paragraph({children:[new TextRun(text)]})]});
const document=new Document({creator:'Pivot synthetic fixture generator',title:'Entirely synthetic manuscript',sections:[{children:[...lines.map(text=>new Paragraph({children:text.startsWith("Reference DOI:") ? [new TextRun("Reference DOI: "),new ExternalHyperlink({link:"https://doi.org/10.1371/journal.pmed.0020124",children:[new TextRun("10.1371/journal.pmed.0020124")]})] : [new TextRun(text)]})),new Table({width:{size:9000,type:WidthType.DXA},columnWidths:[4500,4500],rows:[new TableRow({children:[cell('Synthetic table label'),cell('Synthetic table value')]}),new TableRow({children:[cell('Records'),cell('24 synthetic records')]})]}),new Paragraph({children:[new TextRun('END-OF-SYNTHETIC-DOCUMENT-TRACE-2026')]})]}]});
Packer.toBuffer(document).then(buffer=>fs.writeFileSync(__dirname+'/synthetic-manuscript.docx',buffer));
