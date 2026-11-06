import FormalDocumentPage from '../../../../../components/publishing/formal-documents';
export default async function FormalImportPage({params}:{params:Promise<{manuscriptId:string;importId:string}>}){const {manuscriptId,importId}=await params;return <FormalDocumentPage manuscriptId={manuscriptId} importId={importId}/>;}
