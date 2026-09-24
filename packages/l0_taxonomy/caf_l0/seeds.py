"""Seed data definitions and generator for CA Final New Scheme (2023)."""

from pathlib import Path
import random
import yaml
from caf_l0.ids import CROCKFORD_ALPHABET

# Deterministic random generator for reproducible stable IDs across regenerations
_rng = random.Random(20260924)


def _gen_id(paper_code: str) -> str:
    code = "".join(_rng.choice(CROCKFORD_ALPHABET) for _ in range(6))
    return f"{paper_code}-{code}"


def build_p1_data() -> dict:
    p = "P1"
    chapters = [
        ("Ind AS 116: Leases", [
            ("Scope and Recognition Exemptions", [
                "Identifying a lease contract",
                "Short-term leases and low-value asset exemptions",
                "Separating components of a contract",
            ]),
            ("Lessee Accounting", [
                "Initial measurement of ROU asset and lease liability",
                "Subsequent measurement and depreciation of ROU asset",
                "Lease modifications and scope decrease",
            ]),
            ("Lessor Accounting", [
                "Classification into operating vs finance lease",
                "Finance lease initial and subsequent accounting",
                "Manufacturer or dealer lessor accounting",
                "Sale and leaseback transactions",
            ]),
        ]),
        ("Ind AS 115: Revenue from Contracts with Customers", [
            ("Five-Step Model Core", [
                "Step 1: Identifying the contract with customer",
                "Step 2: Identifying performance obligations",
                "Step 3: Determining the transaction price",
                "Step 4: Allocating transaction price to performance obligations",
                "Step 5: Recognizing revenue over time vs at a point in time",
            ]),
            ("Specific Revenue Scenarios", [
                "Contract costs: incremental costs of obtaining a contract",
                "Licensing agreements and intellectual property",
                "Principal vs agent considerations",
                "Warranties and customer options for additional goods/services",
            ]),
        ]),
        ("Ind AS on Financial Instruments (Ind AS 32, 109, 107)", [
            ("Classification and Measurement", [
                "Financial asset classification: Amortised cost, FVTOCI, FVTPL",
                "Business model and contractual cash flow (SPPI) test",
                "Financial liability classification and compound instruments",
                "Fair value option and reclassifications",
            ]),
            ("Impairment and Hedge Accounting", [
                "Expected credit loss (ECL) model: 3-stage approach",
                "Hedging instruments, hedged items and qualifying criteria",
                "Cash flow hedge vs fair value hedge mechanics",
                "De-recognition of financial assets and liabilities",
            ]),
        ]),
        ("Business Combinations & Corporate Restructuring (Ind AS 103)", [
            ("Acquisition Method", [
                "Identifying the acquirer and acquisition date",
                "Purchase consideration and contingent consideration",
                "Recognizing and measuring identifiable assets and liabilities",
                "Calculation of goodwill or gain on bargain purchase",
            ]),
            ("Common Control and Step Acquisitions", [
                "Business combinations under common control (Appendix C)",
                "Reverse acquisitions mechanics",
                "Step acquisitions and re-measurement of existing interest",
            ]),
        ]),
        ("Consolidated Financial Statements (Ind AS 110, 111, 28)", [
            ("Consolidation Procedures", [
                "Assessment of control under Ind AS 110",
                "Non-controlling interest (NCI) valuation: Proportionate vs Fair value",
                "Uniform accounting policies and intra-group eliminations",
                "Changes in parent's ownership interest without loss of control",
            ]),
            ("Associates and Joint Arrangements", [
                "Equity method of accounting under Ind AS 28",
                "Joint ventures vs joint operations under Ind AS 111",
                "Disposal of subsidiary and loss of control",
            ]),
        ]),
        ("Ind AS on Balance Sheet Items (Ind AS 16, 38, 36, 40, 2, 23)", [
            ("Tangible and Intangible Assets", [
                "Ind AS 16: PPE recognition, component depreciation, revaluation",
                "Ind AS 38: Intangible assets and R&D expenditure",
                "Ind AS 23: Borrowing costs capitalisation criteria",
                "Ind AS 40: Investment property accounting",
            ]),
            ("Valuation and Impairment", [
                "Ind AS 2: Valuation of inventories and NRV testing",
                "Ind AS 36: Identifying Cash Generating Units (CGU)",
                "Ind AS 36: Impairment testing and reversal of impairment",
                "Ind AS 105: Non-current assets held for sale and discontinued ops",
            ]),
        ]),
        ("Ind AS on Employee Benefits & Share Based Payment (Ind AS 19, 102)", [
            ("Employee Benefits (Ind AS 19)", [
                "Short-term and other long-term benefits",
                "Defined contribution vs defined benefit plans",
                "Actuarial assumptions and remeasurement gains/losses in OCI",
            ]),
            ("Share Based Payment (Ind AS 102)", [
                "Equity-settled share based payment transactions",
                "Cash-settled share based payment transactions",
                "Share-based payment with cash alternatives",
            ]),
        ]),
        ("Ind AS on Income Taxes and Other Standards (Ind AS 12, 21, 24, 33)", [
            ("Income Taxes (Ind AS 12)", [
                "Current tax and deferred tax calculation",
                "Tax base vs carrying amount and temporary differences",
                "Recognition of deferred tax asset and unused tax losses",
            ]),
            ("Foreign Exchange & Disclosures", [
                "Ind AS 21: Functional currency and foreign operations translation",
                "Ind AS 33: Basic and diluted earnings per share",
                "Ind AS 24: Related party disclosures",
                "Ind AS 108: Operating segments identification",
            ]),
        ]),
    ]
    return _build_tree(p, "s2023.P1", chapters)


def build_p2_data() -> dict:
    p = "P2"
    chapters = [
        ("Advanced Capital Budgeting Decisions", [
            ("Project Evaluation Techniques", [
                "Cash flow forecasting and inflation adjustments",
                "NPV, IRR and Modified IRR comparison",
                "Capital rationing and project indivisibility",
            ]),
            ("Risk and Uncertainty in Capital Budgeting", [
                "Sensitivity analysis and scenario analysis",
                "Decision tree analysis and certainty equivalent method",
                "Real options in capital budgeting",
            ]),
        ]),
        ("Security Analysis and Valuation", [
            ("Equity Valuation", [
                "Dividend discount models and Walter model",
                "Free Cash Flow to Firm (FCFF) and to Equity (FCFE)",
                "Relative valuation multiples (P/E, P/B, EV/EBITDA)",
            ]),
            ("Bond and Fixed Income Valuation", [
                "Bond yield: YTM, YTC and spot rates",
                "Duration, modified duration and convexity",
                "Term structure of interest rates and immunization",
            ]),
        ]),
        ("Portfolio Management", [
            ("Portfolio Theory and Capital Asset Pricing", [
                "Markowitz portfolio selection and efficient frontier",
                "Capital Asset Pricing Model (CAPM) and Beta estimation",
                "Arbitrage Pricing Theory (APT) and multi-factor models",
            ]),
            ("Portfolio Performance and Rebalancing", [
                "Sharpe, Treynor and Jensen performance measures",
                "Fama decomposition of portfolio return",
                "Portfolio rebalancing strategies: Constant mix, CPPI",
            ]),
        ]),
        ("Derivatives Analysis and Valuation", [
            ("Futures and Forwards", [
                "Pricing of forwards and futures contracts",
                "Hedging strategies using stock and index futures",
                "Commodity futures and roll yield",
            ]),
            ("Option Contracts and Strategies", [
                "Option payoff diagrams and combination strategies",
                "Binomial option pricing model",
                "Black-Scholes-Merton model and Option Greeks",
            ]),
        ]),
        ("Foreign Exchange Exposure and Risk Management", [
            ("Exchange Rate Arithmetic", [
                "Direct vs indirect quotes, cross rates and bid-ask spreads",
                "Purchasing Power Parity (PPP) and Interest Rate Parity (IRP)",
                "International Fisher Effect (IFE)",
            ]),
            ("Forex Hedging Techniques", [
                "Transaction, translation and economic exposure",
                "Internal hedging: Leading, lagging, netting, matching",
                "External hedging: Forward contracts, money market cover, options",
            ]),
        ]),
        ("Interest Rate Risk Management", [
            ("Interest Rate Derivatives", [
                "Forward Rate Agreements (FRAs)",
                "Interest rate futures and hedging debt portfolios",
                "Interest rate swaps: Comparative advantage argument",
                "Interest rate caps, floors and collars",
            ]),
        ]),
        ("Business Valuation and Corporate Restructuring", [
            ("Mergers and Acquisitions", [
                "Financial evaluation of M&A: Swap ratio determination",
                "Post-merger EPS and market price impact",
                "Economic Value Added (EVA) and Market Value Added (MVA)",
                "Takeover defenses and reverse mergers",
            ]),
            ("Startup Finance and Securitization", [
                "Pitch deck, bootstrapping and venture capital stages",
                "Startup valuation methods: Scorecard, Berkus, Venture capital method",
                "Securitization mechanism and pass-through certificates",
            ]),
        ]),
    ]
    return _build_tree(p, "s2023.P2", chapters)


def build_p3_data() -> dict:
    p = "P3"
    chapters = [
        ("Quality Management (SQC 1, SQM 1, SQM 2)", [
            ("Leadership and Firm Governance", [
                "Leadership responsibilities for quality within the firm",
                "Relevant ethical requirements and independence policies",
                "Acceptance and continuance of client relationships",
            ]),
            ("Engagement Performance and Monitoring", [
                "Engagement quality review (EQR) eligibility and procedures",
                "Monitoring and remediation processes",
                "Documentation of the system of quality management",
            ]),
        ]),
        ("General Auditing Principles and Planning (SA 200, 300 series)", [
            ("Fundamental Principles", [
                "SA 200: Overall objectives and professional skepticism",
                "SA 210: Agreeing the terms of audit engagements",
                "SA 220: Quality management for an audit of financial statements",
                "SA 230: Audit documentation and assembly of final audit file",
            ]),
            ("Audit Planning and Materiality", [
                "SA 300: Planning an audit of financial statements",
                "SA 320: Materiality in planning and performing an audit",
                "Performance materiality and revision as audit progresses",
                "SA 450: Evaluation of misstatements identified during the audit",
            ]),
        ]),
        ("Risk Assessment and Internal Control (SA 315, 330, 240)", [
            ("Understanding Entity and Environment", [
                "SA 315: Identifying and assessing risks of material misstatement",
                "Understanding the entity's internal control system",
                "IT general controls (ITGC) and application controls",
            ]),
            ("Responding to Assessed Risks and Fraud", [
                "SA 330: The auditor's responses to assessed risks",
                "Test of controls vs substantive audit procedures",
                "SA 240: The auditor's responsibilities relating to fraud",
                "Fraud risk factors and auditor's inquiry of management",
            ]),
        ]),
        ("Audit Evidence and Sampling (SA 500 series)", [
            ("Obtaining Sufficient Appropriate Evidence", [
                "SA 500: Audit evidence sources and reliability",
                "SA 501: Inventory count attendance and litigation inquiries",
                "SA 505: External confirmations procedures and negative confirmations",
                "SA 520: Analytical procedures in substantive testing",
                "SA 530: Audit sampling and evaluation of sample results",
            ]),
            ("Estimates, Related Parties and Subsequent Events", [
                "SA 540: Auditing accounting estimates and fair value disclosures",
                "SA 550: Related parties identification and undisclosed relationships",
                "SA 560: Subsequent events: Facts known before vs after report date",
                "SA 570: Going concern evaluation and material uncertainty",
                "SA 580: Written representations limitations and reliability",
            ]),
        ]),
        ("Using Work of Others and Group Audits (SA 600 series)", [
            ("Coordinating with Others", [
                "SA 600: Using the work of another auditor in group audits",
                "Principal auditor responsibilities and component auditors",
                "SA 610: Using the work of internal auditors",
                "SA 620: Using the work of an auditor's expert",
            ]),
        ]),
        ("Audit Conclusions and Reporting (SA 700 series)", [
            ("Audit Opinions", [
                "SA 700: Forming an opinion and reporting on financial statements",
                "SA 705: Modifications to the opinion: Qualified, Adverse, Disclaimer",
                "SA 706: Emphasis of matter and other matter paragraphs",
            ]),
            ("Key Audit Matters and Other Information", [
                "SA 701: Communicating Key Audit Matters (KAM) in the report",
                "Determination of KAM vs matters requiring modification",
                "SA 720: The auditor's responsibilities relating to other information",
            ]),
        ]),
        ("Specialized Audits, Digital Auditing and Due Diligence", [
            ("Specialized Audits", [
                "Audit of Banks: IRAC norms and NPA classification",
                "Audit of NBFCs and RBI prudential regulations",
                "Audit of Public Sector Undertakings (PSU) and C&AG role",
            ]),
            ("Forensic Accounting and Digital Assurance", [
                "Digital auditing tools: Data analytics and automated test routines",
                "Due diligence: Financial, commercial and operational review",
                "Forensic investigation techniques and red flags",
                "ESG assurance: Frameworks and auditor readiness",
            ]),
        ]),
        ("Professional Ethics and Code of Conduct", [
            ("First Schedule to CA Act, 1949", [
                "Part I: Professional misconduct for members in practice",
                "Part II: Professional misconduct for members in service",
                "Part III & IV: Misconduct generally and other misconduct",
            ]),
            ("Second Schedule and Council Guidelines", [
                "Part I: Serious misconduct for members in practice",
                "Part II & III: General misconduct and disciplinary mechanisms",
                "ICAI Code of Ethics: Fundamental principles and threats/safeguards",
            ]),
        ]),
    ]
    return _build_tree(p, "s2023.P3", chapters)


def build_p4_data() -> dict:
    p = "P4"
    chapters = [
        ("Profits and Gains of Business or Profession (PGBP)", [
            ("Depreciation and Business Deductions", [
                "Depreciation under section 32 and additional depreciation",
                "Scientific research expenditure (Sec 35) and capital investments",
                "Specific allowable deductions under sections 30 to 37",
            ]),
            ("Disallowances and Special Provisions", [
                "Section 40(a) disallowances: TDS default, payment to non-residents",
                "Section 40A(2) payments to relatives and 40A(3) cash payments",
                "Section 43B statutory dues and recent MSME payment rules",
                "Presumptive taxation under sections 44AD, 44ADA, 44AE",
            ]),
        ]),
        ("Capital Gains and Other Sources", [
            ("Capital Gains Computation", [
                "Transfer definition and slump sale under section 50B",
                "Capital gains exemptions: Section 54, 54EC, 54F",
                "Taxation of virtual digital assets (VDA) under section 115BBH",
                "Buyback of shares and capital reduction tax treatment",
            ]),
            ("Income from Other Sources", [
                "Taxation of gifts and undervalued property (Sec 56(2)(x))",
                "Share premium in excess of fair value (Sec 56(2)(viib))",
                "Dividend income taxation and deductions allowable",
            ]),
        ]),
        ("Assessment of Various Entities & Charitable Trusts", [
            ("Corporate and Entity Taxation", [
                "Minimum Alternate Tax (MAT) under section 115JB",
                "Concessional tax regimes for domestic companies (Sec 115BAA/115BAB)",
                "Taxation of firms, LLPs and Alternate Minimum Tax (AMT)",
                "Taxation of Business Trusts (REITs/InvITs) and Securitization Trusts",
            ]),
            ("Charitable and Religious Trusts", [
                "Registration regime under sections 12AB and 10(23C)",
                "Application of income, accumulation rules and Form 9A/10",
                "Exit tax on accreted income of trusts (Sec 115TD)",
            ]),
        ]),
        ("TDS, TCS, Assessment and Dispute Resolution", [
            ("TDS and TCS Mechanisms", [
                "TDS on contract payments, professional fees and rent",
                "TDS on purchase of goods (Sec 194Q) and TCS on sale of goods (Sec 206C(1H))",
                "TDS on benefit or perquisite in business (Sec 194R)",
            ]),
            ("Assessment, Appeals and Penalties", [
                "Faceless assessment scheme and reassessment under section 147/148",
                "Appeals before CIT(A), ITAT, High Court and Supreme Court",
                "Penalties for under-reporting and misreporting of income (Sec 270A)",
                "General Anti-Avoidance Rules (GAAR) provisions and applicability",
            ]),
        ]),
        ("International Taxation and Transfer Pricing", [
            ("Transfer Pricing", [
                "Associated enterprise definition and international transactions",
                "Arm's length price determination methods",
                "Transfer pricing documentation, master file and CbCR",
                "Safe harbour rules and Advance Pricing Agreements (APA)",
                "Secondary adjustment under section 92CE and thin capitalization (Sec 94B)",
            ]),
            ("Non-Resident Taxation & Treaties", [
                "Residential status and Significant Economic Presence (SEP)",
                "Taxation of royalty, FTS and capital gains for non-residents",
                "Equalisation levy on online advertising and e-commerce supply",
                "Double Taxation Relief under section 90/91 and MLI provisions",
            ]),
        ]),
    ]
    return _build_tree(p, "s2023.P4", chapters)


def build_p5_data() -> dict:
    p = "P5"
    chapters = [
        ("Supply, Charge of Tax and Exemptions under GST", [
            ("Concept of Supply", [
                "Section 7: Meaning and scope of supply with consideration",
                "Schedule I: Activities without consideration",
                "Schedule II: Classification as supply of goods vs services",
                "Schedule III: Non-supplies / negative list",
            ]),
            ("Charge and Exemptions", [
                "Section 9: Forward charge and reverse charge mechanism (RCM)",
                "Composition levy under section 10 and eligibility criteria",
                "Mega exemptions notification for goods and services",
            ]),
        ]),
        ("Place, Time and Value of Supply", [
            ("Place of Supply", [
                "Section 10 & 11 IGST: Place of supply of goods (domestic and import/export)",
                "Section 12 IGST: Place of supply of services (both supplier and recipient in India)",
                "Section 13 IGST: Place of supply where supplier or recipient is outside India",
                "Online Information Database Access and Retrieval (OIDAR) services",
            ]),
            ("Time and Value of Supply", [
                "Section 12 & 13 CGST: Time of supply of goods and services",
                "Section 15 CGST: Transaction value and inclusions/exclusions",
                "Valuation rules for related party and distinct person supplies",
            ]),
        ]),
        ("Input Tax Credit (ITC)", [
            ("Eligibility and Apportionment", [
                "Section 16: Eligibility and conditions for claiming ITC",
                "Section 17(1) & 17(2): Apportionment of credit and Rule 42/43 mechanics",
                "Section 17(5): Blocked credit list and specific exceptions",
            ]),
            ("Special ITC Scenarios", [
                "Section 18: ITC on switchover to/from composition and exempt supplies",
                "Job work provisions and ITC on goods sent for job work",
                "Input Service Distributor (ISD) mechanism and distribution rules",
            ]),
        ]),
        ("GST Procedures, Returns and Refunds", [
            ("Invoicing and Payment", [
                "E-invoicing applicability and exceptions",
                "E-way bill rules and verification in transit",
                "Payment of tax, electronic ledgers and order of utilization",
            ]),
            ("Refunds and Zero Rated Supply", [
                "Refund of unutilized ITC due to inverted duty structure",
                "Refund under zero-rated supplies: LUT vs payment of IGST",
                "Deemed exports and relevant date for refund calculation",
            ]),
        ]),
        ("Audit, Demands, Penalties and Appeals under GST", [
            ("Assessment and Audit", [
                "Self-assessment, provisional assessment and scrutiny of returns",
                "Departmental audit (Sec 65) and special audit (Sec 66)",
                "Inspection, search, seizure and arrest powers",
            ]),
            ("Demands, Penalties and Appeals", [
                "Section 73 & 74: Demands for non-fraud vs fraud cases",
                "Penalties, general offences and detention/confiscation rules",
                "Appeals hierarchy: Appellate Authority, GSTAT, High Court",
                "Advance ruling provisions and rectification of orders",
            ]),
        ]),
        ("Customs Law and Foreign Trade Policy (FTP)", [
            ("Customs Valuation and Classification", [
                "Levy and types of customs duties (BCD, SWS, Anti-dumping, Safeguard)",
                "Customs valuation: Transaction value and Rule 3 to 10 adjustments",
                "Export valuation rules and classification principles",
            ]),
            ("Customs Procedures and FTP", [
                "Clearance of imported goods for home consumption vs warehousing",
                "Manufacture in warehouse (MOOWR scheme)",
                "Duty drawback under sections 74 and 75",
                "Foreign Trade Policy: Advance Authorization and EPCG schemes",
            ]),
        ]),
    ]
    return _build_tree(p, "s2023.P5", chapters)


def build_p6_data() -> dict:
    p = "P6"
    chapters = [
        ("Financial Analysis and Strategic Financial Management", [
            ("Corporate Financial Strategy", [
                "Evaluating strategic investments and hurdle rates",
                "Capital restructuring, dividend decisions and leverage optimization",
                "Forecasting sustainable growth rate and financial distress",
            ]),
            ("Valuation in Complex Business Situations", [
                "Comprehensive DCF and relative valuation under uncertainty",
                "Brand and intangible asset valuation in M&A",
                "Cross-border M&A and currency risk integration",
            ]),
        ]),
        ("Auditing, Internal Controls and Corporate Governance", [
            ("Governance and Risk Oversight", [
                "Board oversight, Audit Committee responsibilities and LODR compliance",
                "Internal financial control evaluation and reporting",
                "Forensic review and proactive fraud risk management",
            ]),
            ("Complex Accounting & Audit Issues", [
                "Evaluating complex Ind AS revenue and lease structures",
                "Group audit considerations and overseas subsidiary oversight",
                "Auditor reporting dilemmas and KAM formulation in crises",
            ]),
        ]),
        ("Direct and International Tax Strategy", [
            ("Domestic Tax Structuring", [
                "Tax-optimized business restructuring: Mergers, demergers, slump sales",
                "Interplay between corporate tax regimes and MAT credit",
                "GAAR evaluation for corporate holding structures",
            ]),
            ("Cross-Border Tax Planning", [
                "BEPS alignment, substance requirements and treaty shopping risks",
                "Supply chain transfer pricing optimization and APA strategy",
                "Managing permanent establishment and SEP exposure",
            ]),
        ]),
        ("Indirect Tax Optimization and Supply Chain Strategy", [
            ("GST Structuring", [
                "Supply chain design: Cross-charge vs ISD vs branch transfers",
                "Optimizing ITC recovery and mitigating inverted duty impact",
                "Export competitiveness: Advance authorization vs GST refunds",
            ]),
            ("Customs and FTP Integration", [
                "Customs duty mitigation via Free Trade Agreements (FTA)",
                "Special Economic Zones (SEZ) and bonded warehouse logistics",
                "Regulatory dispute management in multi-jurisdictional supply",
            ]),
        ]),
        ("Comprehensive Integrated Case Studies", [
            ("Enterprise Turnaround and Distress", [
                "Insolvency and Bankruptcy Code (IBC) financial and tax implications",
                "Debt restructuring, one-time settlement and haircut accounting",
                "Stakeholder negotiation and turnaround strategy implementation",
            ]),
            ("Cross-Border Expansion and IPO Readiness", [
                "Preparing financial statements for global listing / IPO",
                "Multi-regulatory compliance: Companies Act, SEBI, FEMA, Competition Act",
                "Integrated reporting and ESG governance implementation",
            ]),
        ]),
    ]
    return _build_tree(p, "s2023.P6", chapters)


def _build_tree(paper_code: str, paper_id: str, chapter_data: list) -> dict:
    chapters_out = []
    for c_idx, (c_name, topics) in enumerate(chapter_data, start=1):
        c_id = _gen_id(paper_code)
        topics_out = []
        for t_idx, (t_name, subtopics) in enumerate(topics, start=1):
            t_id = _gen_id(paper_code)
            subtopics_out = []
            for s_idx, s_name in enumerate(subtopics, start=1):
                s_id = _gen_id(paper_code)
                subtopics_out.append({"id": s_id, "name": s_name, "seq": s_idx})
            topics_out.append({"id": t_id, "name": t_name, "seq": t_idx, "subtopics": subtopics_out})
        chapters_out.append({"id": c_id, "name": c_name, "seq": c_idx, "topics": topics_out})

    return {
        "paper": paper_id,
        "sm_edition": "Applicable for May 2024 onwards",
        "chapters": chapters_out,
    }


def generate_all_papers(target_dir: Path) -> dict[str, dict]:
    target_dir.mkdir(parents=True, exist_ok=True)
    all_papers = {
        "P1": build_p1_data(),
        "P2": build_p2_data(),
        "P3": build_p3_data(),
        "P4": build_p4_data(),
        "P5": build_p5_data(),
        "P6": build_p6_data(),
    }
    for code, data in all_papers.items():
        out_file = target_dir / f"{code}.yaml"
        with open(out_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, sort_keys=False, allow_unicode=True)
    return all_papers


def generate_all_weightages(target_dir: Path, papers_data: dict[str, dict]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for code, tree in papers_data.items():
        chapters = tree["chapters"]
        n_ch = len(chapters)
        # Partition chapters into 3-4 sections with realistic ICAI weightage percentages
        if n_ch <= 5:
            splits = [n_ch]
            ranges = [(85.0, 100.0)]
        elif n_ch <= 8:
            mid = n_ch // 2
            splits = [mid, n_ch - mid]
            ranges = [(45.0, 55.0), (45.0, 55.0)]
        else:
            p1 = n_ch // 3
            p2 = n_ch // 3
            p3 = n_ch - p1 - p2
            splits = [p1, p2, p3]
            ranges = [(25.0, 35.0), (30.0, 40.0), (30.0, 40.0)]

        sections = []
        cur = 0
        for i, count in enumerate(splits, start=1):
            ch_subset = chapters[cur : cur + count]
            cur += count
            min_p, max_p = ranges[i - 1]
            sections.append({
                "id": f"{code}_SEC{i}",
                "name": f"Section {i} Core Modules",
                "min_pct": min_p,
                "max_pct": max_p,
                "chapter_ids": [c["id"] for c in ch_subset],
            })

        out_file = target_dir / f"{code}.yaml"
        with open(out_file, "w", encoding="utf-8") as f:
            yaml.dump({"paper": tree["paper"], "sections": sections}, f, sort_keys=False)
