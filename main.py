from fastapi import FastAPI

from config import settings
from routers import banking, branch
from routers import health, sales, tickets, user

app = FastAPI(title=settings.app_name)

app.include_router(health.router)
app.include_router(sales.router)
app.include_router(tickets.router)
app.include_router(banking.router)
app.include_router(branch.router)
app.include_router(user.router)
