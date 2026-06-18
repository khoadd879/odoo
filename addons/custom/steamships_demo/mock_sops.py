"""
Steamships SOP knowledge base - 15 sample documents.

Used by:
  - Mock chatbot (controller/ai_chatbot.py) when ANTHROPIC_API_KEY is not set.
  - Future: as seed data for pgvector RAG when real LLM is enabled.

Search is naive keyword matching; good enough for the mock.
"""

# Each SOP: id, title, keywords, content, visibility
# visibility: 'staff' = internal only (price list, internal SOPs)
#             'public' = safe for both staff AND client
SOPS = [
    {
        'id': 'sop-001',
        'title': 'FCL 20ft Container - Standard Pricing',
        'keywords': ['fcl', '20ft', '20', 'container', 'shipping', 'price'],
        'content': 'FCL 20ft shipping from Lae/Motukea: PGK 4,500/box list. Includes lift-on/lift-off, 14 days free time at depot. Subject to fuel surcharge. USD Corporate rate: 5% discount.',
        'visibility': 'staff',
        'confidence': 0.95,
    },
    {
        'id': 'sop-002',
        'title': 'FCL 40ft Container - Standard Pricing',
        'keywords': ['fcl', '40ft', '40', 'container', 'shipping', 'price'],
        'content': 'FCL 40ft shipping: PGK 7,800/box list. Same terms as 20ft.',
        'visibility': 'staff',
        'confidence': 0.95,
    },
    {
        'id': 'sop-003',
        'title': 'LCL Cargo Pricing',
        'keywords': ['lcl', 'cbm', 'cubic', 'consolidated', 'small'],
        'content': 'LCL: PGK 280/CBM, minimum 1 CBM. Consolidation from Lae/Motukea to international destinations.',
        'visibility': 'staff',
        'confidence': 0.92,
    },
    {
        'id': 'sop-004',
        'title': 'Stevedoring Charges',
        'keywords': ['stevedoring', 'labor', 'loading', 'unloading', 'mt'],
        'content': 'Stevedoring: PGK 85/metric ton. Includes lashing and securing.',
        'visibility': 'staff',
        'confidence': 0.93,
    },
    {
        'id': 'sop-005',
        'title': 'Tug Assist Services',
        'keywords': ['tug', 'boat', 'berthing', 'pilot'],
        'content': 'Tug assist: PGK 6,500/hour, minimum 2 hours. Required for all vessels over 200m LOA.',
        'visibility': 'staff',
        'confidence': 0.91,
    },
    {
        'id': 'sop-006',
        'title': 'Office Lease - Grade A',
        'keywords': ['office', 'lease', 'grade a', 'pom', 'central'],
        'content': 'Grade A office: PGK 95/sqm/month. Fully fitted, central POM CBD, 24/7 security, backup power.',
        'visibility': 'staff',
        'confidence': 0.90,
    },
    {
        'id': 'sop-007',
        'title': 'Warehouse Lease',
        'keywords': ['warehouse', 'industrial', 'storage', 'dock'],
        'content': 'Industrial warehouse: PGK 45/sqm/month. Loading dock, Motukea or Lae locations.',
        'visibility': 'staff',
        'confidence': 0.90,
    },
    {
        'id': 'sop-008',
        'title': 'Hotel Standard Room',
        'keywords': ['hotel', 'room', 'standard', 'night', 'accommodation'],
        'content': 'Standard king room: PGK 650/night. Includes breakfast and WiFi. Subject to availability.',
        'visibility': 'staff',
        'confidence': 0.92,
    },
    {
        'id': 'sop-009',
        'title': 'Hotel Executive Suite',
        'keywords': ['suite', 'executive', 'hotel', 'vip', 'airport'],
        'content': 'Executive suite: PGK 1,450/night. Lounge access, complimentary airport transfer.',
        'visibility': 'staff',
        'confidence': 0.92,
    },
    {
        'id': 'sop-010',
        'title': 'KYC Document Checklist',
        'keywords': ['kyc', 'onboarding', 'documents', 'compliance', 'checklist'],
        'content': 'KYC documents required: (1) IPA Certificate of Compliance, (2) Tax ID (TIN), (3) Bank reference, (4) Directors ID copies, (5) PEP/sanctions check, (6) Credit check, (7) Insurance certificate, (8) Master service agreement.',
        'visibility': 'public',
        'confidence': 0.95,
    },
    {
        'id': 'sop-011',
        'title': 'Discount Approval Threshold',
        'keywords': ['discount', 'approval', 'manager', 'threshold'],
        'content': 'Discount > 10% off list price requires sales manager approval. Use the "Request Approval" button on the sale order. Approvals are logged with reviewer and rationale.',
        'visibility': 'staff',
        'confidence': 0.94,
    },
    {
        'id': 'sop-012',
        'title': 'Customs Clearance Process',
        'keywords': ['customs', 'clearance', 'broker', 'duty', 'png'],
        'content': 'Customs broker fee: PGK 1,500/shipment. Includes lodgement, duty calculation, liaising with PNG Customs. Standard turnaround: 2-3 business days.',
        'visibility': 'public',
        'confidence': 0.93,
    },
    {
        'id': 'sop-013',
        'title': 'Currency and Pricing',
        'keywords': ['currency', 'pgk', 'usd', 'forex', 'rate'],
        'content': 'Quotations issued in PGK (Papua New Guinean Kina) by default. USD Corporate pricelist available for multinational customers. FX rate reviewed quarterly.',
        'visibility': 'staff',
        'confidence': 0.88,
    },
    {
        'id': 'sop-014',
        'title': 'Branches and Coverage',
        'keywords': ['branch', 'office', 'location', 'lae', 'pom', 'motukea', 'daru'],
        'content': 'Branches: Port Moresby (HQ, Shipping), Lae (Logistics), Motukea (Container Depot), Daru (Western Province Shipping).',
        'visibility': 'public',
        'confidence': 0.96,
    },
    {
        'id': 'sop-015',
        'title': 'Conference Room Booking',
        'keywords': ['conference', 'meeting', 'room', 'hotel', 'event'],
        'content': 'Conference room: PGK 2,500/day, up to 20 pax. Includes AV equipment, morning/afternoon tea. Book through Steamships Hotels sales team.',
        'visibility': 'staff',
        'confidence': 0.90,
    },
]


def search_sops(query, top_k=3, visibility=None):
    """Return top-k SOPs ranked by keyword overlap with query.

    Args:
        query: user question
        top_k: max results
        visibility: None = all; ('public',) = client-safe only;
                    ('public', 'staff') = both modes (staff default)

    Naive: lowercased token intersection count.
    """
    if not query:
        return []
    if visibility is None:
        visibility = ('public', 'staff')
    query_tokens = set(query.lower().split())
    scored = []
    for sop in SOPS:
        if sop.get('visibility', 'staff') not in visibility:
            continue
        sop_tokens = set(sop['keywords'])
        # Also match words in title/content
        content_tokens = set(sop['content'].lower().split())
        overlap = len(query_tokens & (sop_tokens | content_tokens))
        if overlap:
            scored.append((overlap, sop))
    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:top_k]]
