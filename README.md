# 🏦 Arth - Personal Finance System

An internal, agentic personal-finance system that automatically ingests data, answers financial questions, and surfaces insights through a weekly dashboard.

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.12+ (for local development)
- Git

### Running the Application

1. **Clone and navigate to the project:**
   ```bash
   git clone <your-repo-url>
   cd arth
   ```

2. **Start the entire stack:**
   ```bash
   docker-compose up
   ```

3. **Access the application:**
   - **Web Dashboard:** http://localhost:8000
   - **API Documentation:** http://localhost:8000/docs
   - **Health Check:** http://localhost:8000/v1/healthz

### CLI Usage

The Arth CLI provides tools for manual data management:

```bash
# Install in development mode
pip install -e .[dev]

# Check system status
arth status

# Future CLI commands (available in M-3):
arth edit add-txn --account 1 --date 2025-07-01 --amount 2500 --type fee --dry-run
arth edit update-holding --id 12 --qty 150
arth edit reprice-asset --symbol INFY --price 1785.50 --date 2025-07-09
```

## 🏗️ Architecture

### Technology Stack
- **Backend:** Python 3.12, FastAPI, SQLModel
- **Database:** PostgreSQL 16
- **Frontend:** HTMX + Tailwind CSS
- **Infrastructure:** Docker, GitHub Actions
- **Data Processing:** Gmail API, pandas

### Directory Structure
```
arth/
├── src/
│   ├── models/        # SQLModel ORM classes, enums
│   ├── etl/           # Gmail client, parsers, loaders
│   ├── calc/          # KPI functions + SQL helpers
│   ├── api/           # FastAPI routers & HTMX endpoints
│   ├── cli/           # CLI entry-points
│   └── util/          # logging, settings, email helpers
├── scripts/           # one-off backfill, data dumps
├── tests/             # unit + integration + fixtures
├── alembic/           # database migrations
└── docs/              # PRD, TRD, implementation plans
```

## 🛠️ Development

### Local Development Setup

1. **Install dependencies:**
   ```bash
   pip install -e .[dev]
   ```

2. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

3. **Run the development server:**
   ```bash
   uvicorn src.api.main:app --reload
   ```

4. **Run tests:**
   ```bash
   pytest
   ```

5. **Code quality checks:**
   ```bash
   ruff check .          # Linting
   ruff format .         # Formatting
   mypy src/             # Type checking
   ```

### Database Management

```bash
# Create a new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

## 📊 Features (Roadmap)

### ✅ M-0: Repository Bootstrap (Completed)
- [x] Project structure and dependencies
- [x] Docker containerization
- [x] Database models and migrations
- [x] CI pipeline with GitHub Actions
- [x] Basic API and CLI structure

### ⏳ M-1: Ingestion MVP (Planned)
- [ ] Gmail OAuth integration
- [ ] Email parsing and data extraction
- [ ] ETL pipeline implementation

### ⏳ M-2: Calculation & Dashboard Alpha (Planned)
- [ ] KPI calculation engine
- [ ] FastAPI + HTMX dashboard
- [ ] Basic financial metrics

### ⏳ M-3: Parser Coverage & CLI (Planned)
- [ ] Comprehensive email parsers
- [ ] CLI data management tools
- [ ] Enhanced test coverage

### ⏳ M-4: Hardening & UAT (Planned)
- [ ] Error monitoring and alerts
- [ ] Security review
- [ ] User acceptance testing

### ⏳ M-5: Go-Live (Target: July 29, 2025)
- [ ] Production deployment
- [ ] Data backfill
- [ ] Monitoring and maintenance

## 🔒 Security

- OAuth 2.0 for Gmail integration
- Encrypted token storage
- HTTPS enforcement
- Container security best practices
- No sensitive data in logs

## 📖 Documentation

- **[Product Requirements Document](docs/arth_prd_v_1.md)** - What we're building and why
- **[Technical Requirements Document](docs/arth_trd_v_1.md)** - How we're building it
- **[Implementation Plans](docs/Implementation_plans/)** - Step-by-step execution

## 🤝 Contributing

This is an internal project for personal use. For questions or issues, contact the development team.

## 📄 License

Private project - All rights reserved.
A personal financial intelligence system
