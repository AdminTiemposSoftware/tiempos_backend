# tiempos_backend

## Architecture
- FastAPI app with routers per resource.
- Config is loaded from environment variables in app/config.py.
- Database access lives in app/db.py using SQLAlchemy Core and MSSQL table reflection.
- Endpoints return rows from configured tables to keep the API minimal at the start.

## File layout
- app/main.py: Application entry point.
- app/config.py: Environment configuration and defaults.
- app/db.py: Connection pool and shared data access helpers.
- app/routers/: Route modules for each endpoint group.
- .env.example: Sample environment variables.

## Setup
1) Create a virtual environment.
2) Install dependencies:
   pip install -r requirements.txt
3) Copy .env.example to .env and update DATABASE_URL.
4) Start the API:
   uvicorn app.main:app --reload

## Endpoints
- GET /health
- GET /sales
- GET /tickets
- GET /branch
- GET /branch/{branch_id}
- POST /branch
- PUT /branch/{branch_id}
- DELETE /branch/{branch_id}

## MSSQL connection string
Example for ODBC Driver 17:
DATABASE_URL=mssql+pyodbc://USER:PASSWORD@SERVER:1433/DBNAME?driver=ODBC+Driver+17+for+SQL+Server

If you use a named instance or a different driver, update the URL accordingly.
