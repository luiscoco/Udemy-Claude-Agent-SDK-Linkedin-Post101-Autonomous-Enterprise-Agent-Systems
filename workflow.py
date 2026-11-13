"""Lesson-specific workflow. Read this file before the execution adapter."""
from __future__ import annotations
import asyncio
import json
from pathlib import Path
from runtime import atomic_json, contained_path, in_process_tool

async def run(agent, data):
    sources = data['sources']
    if not sources or len({s['id'] for s in sources}) != len(sources) or any(s['risk_points'] < 0 for s in sources):
        raise ValueError('Use unique source IDs with nonnegative policy risk points')
    risk = sum(source['risk_points'] for source in sources)
    policy_decision = 'human_review_required' if risk >= data['escalation_threshold'] else 'routine_review'
    findings = await agent.ask('researcher', 'Summarize only the supplied vendor facts and cite their exact source IDs.', {'vendor': data['vendor'], 'sources': sources},
                               {'findings': [{'fact': source['fact'], 'source_id': source['id']} for source in sources]})
    ids = {source['id'] for source in sources}
    if any(finding['source_id'] not in ids for finding in findings['findings']):
        raise ValueError('Research cited an unknown source')
    draft = await agent.ask('analyst', 'Draft a vendor-risk brief from the findings and deterministic policy decision. Do not approve the vendor.',
        {'vendor': data['vendor'], 'findings': findings, 'risk_points': risk, 'policy_decision': policy_decision},
        'Example Supplies has a pending security review [S1] and a support policy [S2]. Three risk points require human review. No vendor approval has been issued.')
    critique = await agent.ask('critic', 'Check source coverage and respect for the policy decision.', {'draft': draft, 'sources': sources, 'policy_decision': policy_decision},
                               {'accepted': True, 'reason': 'The pending review and absence of approval are explicit.'})
    complete_citations = all('[' + source_id + ']' in draft for source_id in ids)
    accepted = critique['accepted'] and complete_citations
    decision = 'approved_local_report' if accepted and agent.approve else 'pending_human_review'
    audit = {'owner': data['owner'], 'vendor': data['vendor'], 'risk_points': risk, 'policy_decision': policy_decision, 'report_decision': decision, 'mode': agent.live}
    atomic_json(agent.root / 'state/last_audit.json', audit)
    if decision == 'approved_local_report':
        (agent.output / 'approved_report.md').write_text(draft, encoding='utf8')
    return {'findings': findings, 'draft': draft, 'critique': critique, 'citation_gate': complete_citations, 'audit': audit, 'vendor_approved': False}
