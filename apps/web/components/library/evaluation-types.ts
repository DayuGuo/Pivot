import type { DossierData } from './types';
export type Assessment = {
    verdict: 'supported' | 'unsupported' | 'uncertain' | null;
    note: string;
};
export type EvaluationCitation = {
    kind: 'text' | 'metadata';
    field_path: string | null;
    label: string;
    quote: string;
    start: number;
    end: number;
};
export type RegisteredPacket = {
    schema: string;
    package_id: string;
    evaluator_code: string;
    source: {
        version_id: string;
        version_no: number;
        content_digest: string;
        data: DossierData;
        text: string;
    };
    claims: {
        id: string;
        text: string;
        citations: EvaluationCitation[];
        assessment: Assessment;
    }[];
};
export type ReturnReceipt = {
    id: string;
    package_id: string;
    version_id: string;
    digest: string;
    return_no: number;
    created_at: string;
    submitted_by: string;
};
export type EvaluationDetail = {
    id: string;
    answer_id: string;
    evaluator_code: string;
    version_id: string;
    version_no: number;
    is_current: boolean;
    packet_digest: string;
    packet: RegisteredPacket;
    latest: ReturnReceipt | null;
};
export type EvaluationOverview = {
    version_id: string;
    version_no: number;
    content_digest: string;
    packages: {
        id: string;
        evaluator_code: string;
        latest: ReturnReceipt | null;
    }[];
    summary: {
        registered_slots: number;
        confirmed_slots: number;
        disputed_claims: number;
        claims: {
            claim_bucket: string;
            claim_index: number;
            text: string;
            supported: number;
            unsupported: number;
            uncertain: number;
            unanswered: number;
            disagreement: boolean;
            opinions: ({
                evaluator_code: string;
                return_id: string | null;
            } & Assessment)[];
        }[];
    };
};
export const verdictLabel = { supported: '有依据', unsupported: '无依据', uncertain: '待核对' };
