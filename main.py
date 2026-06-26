from fastapi import FastAPI
from contextlib import asynccontextmanager

from config import settings
from routers import auth, banking, branch, draw, ticket
from routers import health, sales, user, number, report
from db import start_scheduler, stop_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()

app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(health.router)
app.include_router(sales.router)
app.include_router(auth.router)
app.include_router(ticket.router)
app.include_router(draw.router)
app.include_router(draw.draw_schedule_router)
app.include_router(draw.draw_schedule_branch_router)
app.include_router(draw.draw_day_router)
app.include_router(banking.router)
app.include_router(branch.router)
app.include_router(user.router)
app.include_router(number.router)
app.include_router(report.router)