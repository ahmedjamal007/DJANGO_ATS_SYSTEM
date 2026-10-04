"""
The demo corpus: resumes and jobs, each tagged with a field of work.

The `category` on both sides is the ground truth that makes calibration
possible. A resume and a job in the same category are a pair that *should*
match; different categories *should not*. Without labels like these,
choosing SKILL_MATCH_THRESHOLD is guesswork -- which is exactly what the
calibrate_threshold command exists to replace.

Resume text is English because that is what candidates submit; the interface
around it is Arabic.
"""

BACKEND = "backend"
FRONTEND = "frontend"
DATA = "data"
DEVOPS = "devops"
HOSPITALITY = "hospitality"
FINANCE = "finance"


class Resume:
    """One sample candidate: a file on disk plus the text inside it."""

    def __init__(self, filename, full_name, headline, location, category, lines):
        self.filename = filename
        self.full_name = full_name
        self.headline = headline
        self.location = location
        self.category = category
        self.lines = lines

    @property
    def email(self):
        # Stable and obviously fake, so seeded accounts are easy to spot.
        slug = self.full_name.lower().replace(" ", ".")
        return f"{slug}@seeker.test"

    @property
    def text(self):
        return "\n".join(self.lines)


class Job:
    """One sample posting."""

    def __init__(self, title, category, location, description, skills,
                 employment_type="full_time", salary_min=None, salary_max=None):
        self.title = title
        self.category = category
        self.location = location
        self.description = description
        self.skills = skills
        self.employment_type = employment_type
        self.salary_min = salary_min
        self.salary_max = salary_max


RESUMES = [
    Resume(
        "backend_developer_cv.pdf", "Mohammed Osman",
        "Backend engineer, Django and PostgreSQL", "الخرطوم", BACKEND,
        [
            "Mohammed Osman",
            "Backend Engineer - Khartoum, Sudan",
            "mohammed.osman@example.com | +249 91 234 5678",
            "",
            "EXPERIENCE",
            "Built and maintained REST APIs for a billing platform using Django and Python",
            "Designed relational schemas and tuned slow PostgreSQL queries with EXPLAIN",
            "Wrote unit and integration tests achieving high coverage on the payments module",
            "Automated deployment with Docker containers and GitHub Actions pipelines",
            "Mentored two junior developers through code review and pair programming",
            "",
            "EDUCATION",
            "BSc Computer Science, University of Khartoum",
        ],
    ),
    Resume(
        "backend_engineer_two.pdf", "Yousif Adam",
        "Server-side developer, APIs and integrations", "أم درمان", BACKEND,
        [
            "Yousif Adam",
            "Software Engineer - Omdurman, Sudan",
            "",
            "EXPERIENCE",
            "Developed and documented HTTP APIs in Python for a logistics company",
            "Modelled orders and shipments in a relational database and wrote the migrations",
            "Integrated a third-party payment gateway including retry and reconciliation logic",
            "Added a caching layer with Redis that cut average response time in half",
            "Kept the continuous integration pipeline green and the test suite meaningful",
            "",
            "EDUCATION",
            "BSc Software Engineering, Sudan University of Science and Technology",
        ],
    ),
    Resume(
        "frontend_developer_cv.docx", "Salma Idris",
        "Web developer, React and TypeScript", "أم درمان", FRONTEND,
        [
            "Salma Idris",
            "Web Developer - Omdurman, Sudan",
            "salma.idris@example.com | +249 92 345 6789",
            "",
            "EXPERIENCE",
            "Built single-page apps with Next.js and Redux for a retail customer portal",
            "Implemented reusable component libraries and design systems in TypeScript",
            "Improved page load times by code splitting and lazy loading heavy routes",
            "Worked closely with designers to deliver responsive layouts across devices",
            "",
            "EDUCATION",
            "BSc Software Engineering, Sudan University of Science and Technology",
        ],
    ),
    Resume(
        "frontend_developer_two.docx", "Rania Bashir",
        "Interface developer, accessibility focus", "الخرطوم", FRONTEND,
        [
            "Rania Bashir",
            "Frontend Developer - Khartoum, Sudan",
            "",
            "EXPERIENCE",
            "Built browser interfaces with modern JavaScript frameworks and component state",
            "Made dashboards usable on small screens with responsive CSS and flexible grids",
            "Audited pages for accessibility and fixed keyboard navigation and contrast issues",
            "Wrote browser tests covering the checkout journey end to end",
            "",
            "EDUCATION",
            "BSc Computer Science, Al-Neelain University",
        ],
    ),
    Resume(
        "data_analyst_cv.pdf", "Fatima Ali",
        "Data analyst, SQL and reporting", "الخرطوم", DATA,
        [
            "Fatima Ali",
            "Data Analyst - Khartoum, Sudan",
            "",
            "EXPERIENCE",
            "Wrote complex SQL queries against a data warehouse to answer commercial questions",
            "Built and maintained dashboards that the operations team relies on daily",
            "Cleaned and reconciled messy source data before it reached reporting",
            "Analysed subscriber churn with Python and pandas and presented the findings",
            "",
            "EDUCATION",
            "BSc Statistics, University of Khartoum",
        ],
    ),
]

RESUMES += [
    Resume(
        "data_scientist_cv.pdf", "Osman Khalid",
        "Data scientist, forecasting and modelling", "بورتسودان", DATA,
        [
            "Osman Khalid",
            "Data Scientist - Port Sudan, Sudan",
            "",
            "EXPERIENCE",
            "Built demand forecasting models in Python and measured them against a baseline",
            "Engineered features from transactional data and validated them with cross validation",
            "Queried large tables in SQL to assemble training datasets",
            "Explained model behaviour to commercial stakeholders in plain language",
            "",
            "EDUCATION",
            "MSc Applied Statistics, University of Khartoum",
        ],
    ),
    Resume(
        "devops_engineer_cv.pdf", "Tariq Nour",
        "Infrastructure and deployment", "الخرطوم", DEVOPS,
        [
            "Tariq Nour",
            "DevOps Engineer - Khartoum, Sudan",
            "",
            "EXPERIENCE",
            "Ran containerised workloads in production and handled rollouts and rollbacks",
            "Built continuous delivery pipelines that test, build and ship on every merge",
            "Managed Linux servers, monitoring and alerting for a national service",
            "Wrote infrastructure as code so environments could be rebuilt from scratch",
            "Responded to incidents on call and wrote the follow-up reviews",
            "",
            "EDUCATION",
            "BSc Computer Engineering, Sudan University of Science and Technology",
        ],
    ),
    Resume(
        "chef_cv.pdf", "Tariq Hassan",
        "Head chef, seafood kitchens", "بورتسودان", HOSPITALITY,
        [
            "Tariq Hassan",
            "Head Chef - Port Sudan, Sudan",
            "tariq.hassan@example.com | +249 93 456 7890",
            "",
            "EXPERIENCE",
            "Ran the kitchen of a busy seafood restaurant serving two hundred covers a night",
            "Designed seasonal menus around locally sourced fish and vegetables",
            "Trained and supervised a brigade of eight kitchen staff",
            "Controlled food cost and managed supplier relationships and stock rotation",
        ],
    ),
    Resume(
        "accountant_cv.pdf", "Amna Siddig",
        "Accountant, reporting and audit", "الخرطوم", FINANCE,
        [
            "Amna Siddig",
            "Accountant - Khartoum, Sudan",
            "",
            "EXPERIENCE",
            "Prepared monthly management accounts and the year end financial statements",
            "Reconciled bank accounts and supplier ledgers and resolved long standing differences",
            "Supported the external audit and prepared the requested schedules",
            "Managed payroll for a company of ninety staff",
            "",
            "EDUCATION",
            "BSc Accounting, University of Khartoum",
        ],
    ),
    Resume(
        "finance_officer_cv.pdf", "Khalid Omer",
        "Finance officer, budgeting and controls", "أم درمان", FINANCE,
        [
            "Khalid Omer",
            "Finance Officer - Omdurman, Sudan",
            "",
            "EXPERIENCE",
            "Built and monitored departmental budgets and explained variances to managers",
            "Processed supplier payments and maintained the purchase approval controls",
            "Produced cash flow forecasts that guided short term financing decisions",
            "Improved the month end close process and shortened it by four days",
            "",
            "EDUCATION",
            "BSc Business Administration, Al-Neelain University",
        ],
    ),
]


# Three employers. The seed command creates them in this order.
COMPANIES = [
    {
        "email": "hr@sudatel.test",
        "name": "سوداتل للاتصالات",
        "location": "الخرطوم",
        "description": "شركة اتصالات سودانية تقدّم خدمات الهاتف والإنترنت.",
        "website": "https://example.com/sudatel",
    },
    {
        "email": "hr@bok.test",
        "name": "بنك الخرطوم",
        "location": "الخرطوم",
        "description": "أحد أقدم البنوك في السودان.",
        "website": "https://example.com/bok",
    },
    {
        "email": "hr@nileside.test",
        "name": "مجموعة النيل للضيافة",
        "location": "بورتسودان",
        "description": "مطاعم وفنادق على ساحل البحر الأحمر.",
        "website": "https://example.com/nileside",
    },
]

# Skill lines describe the work, not the credential -- see the README section
# on how wording changes the score.
JOBS = [
    Job("Backend Engineer", BACKEND, "الخرطوم",
        "Build and maintain the server-side services behind our subscriber portal. "
        "You will design HTTP APIs and model data in a relational database.",
        ["building REST APIs with Django and Python",
         "optimising slow PostgreSQL queries",
         "automated testing and continuous integration"],
        salary_min=600000, salary_max=1100000),
    Job("Senior Python Developer", BACKEND, "الخرطوم",
        "Lead development of the billing platform and mentor the junior engineers "
        "on the team. Most of the work is server-side Python.",
        ["writing maintainable Python services",
         "designing relational database schemas",
         "reviewing code and mentoring other developers"],
        salary_min=900000, salary_max=1500000),
    Job("API Integration Developer", BACKEND, "أم درمان",
        "Connect our platform to partner systems: payment gateways, SMS providers "
        "and the national switch.",
        ["integrating third-party payment gateways",
         "documenting HTTP APIs for other teams",
         "handling retries and reconciliation for failed requests"],
        salary_min=550000, salary_max=950000),
    Job("Frontend Developer", FRONTEND, "الخرطوم",
        "Build the customer-facing web application for self-service. You will work "
        "closely with designers.",
        ["building single-page applications with React",
         "writing reusable interface components in TypeScript",
         "making layouts work across phones and desktops"],
        salary_min=500000, salary_max=900000),
    Job("UI Engineer", FRONTEND, "أم درمان",
        "Own the look and behaviour of our dashboards in the browser.",
        ["building browser interfaces with modern JavaScript",
         "improving page load performance",
         "making pages usable with a keyboard and a screen reader"],
        employment_type="remote", salary_min=450000, salary_max=850000),
    Job("Data Analyst", DATA, "الخرطوم",
        "Answer commercial questions with data and keep the reporting the "
        "operations team depends on running.",
        ["writing complex SQL queries against a warehouse",
         "building dashboards for non-technical teams",
         "cleaning and reconciling messy source data"],
        salary_min=500000, salary_max=900000),
    Job("Data Scientist", DATA, "الخرطوم",
        "Build predictive models that inform commercial decisions.",
        ["building and evaluating predictive models in Python",
         "engineering features from transactional data",
         "explaining model results to business stakeholders"],
        salary_min=800000, salary_max=1400000),
    Job("Business Intelligence Developer", DATA, "بورتسودان",
        "Turn raw operational data into reporting the branch network can act on.",
        ["modelling data for reporting",
         "writing SQL for large analytical queries",
         "maintaining scheduled data pipelines"],
        salary_min=550000, salary_max=950000),
    Job("DevOps Engineer", DEVOPS, "الخرطوم",
        "Keep our services running and make deployments boring.",
        ["running containerised workloads in production",
         "building continuous delivery pipelines",
         "administering Linux servers and monitoring"],
        salary_min=700000, salary_max=1300000),
    Job("Site Reliability Engineer", DEVOPS, "الخرطوم",
        "Own availability: monitoring, alerting, and the on-call rota.",
        ["responding to production incidents",
         "setting up monitoring and alerting",
         "writing infrastructure as code"],
        salary_min=750000, salary_max=1400000),
    Job("Accountant", FINANCE, "الخرطوم",
        "Prepare the monthly management accounts and support the annual audit.",
        ["preparing monthly management accounts",
         "reconciling bank and supplier ledgers",
         "supporting an external audit"],
        salary_min=400000, salary_max=750000),
    Job("Finance Officer", FINANCE, "أم درمان",
        "Manage budgets, payments and the month end close.",
        ["building and monitoring departmental budgets",
         "processing supplier payments with proper controls",
         "producing cash flow forecasts"],
        salary_min=380000, salary_max=700000),
    Job("Payroll Specialist", FINANCE, "الخرطوم",
        "Run payroll accurately and on time for a growing headcount.",
        ["managing payroll for a large workforce",
         "applying tax and social insurance rules",
         "resolving pay queries from staff"],
        employment_type="part_time", salary_min=300000, salary_max=550000),
    Job("Head Chef", HOSPITALITY, "بورتسودان",
        "Run the kitchen of our flagship seafood restaurant.",
        ["running a busy restaurant kitchen",
         "designing seasonal menus around local produce",
         "training and supervising kitchen staff"],
        salary_min=450000, salary_max=800000),
    Job("Restaurant Operations Manager", HOSPITALITY, "بورتسودان",
        "Own the day-to-day running of two restaurants on the coast.",
        ["controlling food cost and stock",
         "managing supplier relationships",
         "leading a front of house team"],
        salary_min=500000, salary_max=900000),
]
