from fastapi import FastAPI

from config import settings
from routers import branch
from routers import health, sales, tickets

app = FastAPI(title=settings.app_name)

app.include_router(health.router)
app.include_router(sales.router)
app.include_router(tickets.router)
app.include_router(branch.router)
