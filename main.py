from fastapi import FastAPI

from config import settings
from routers import banking, branch, draw, ticket
from routers import health, sales, user

app = FastAPI(title=settings.app_name)

app.include_router(health.router)
app.include_router(sales.router)
app.include_router(ticket.router)
app.include_router(draw.router)
app.include_router(draw.draw_schedule_router)
app.include_router(draw.draw_schedule_branch_router)
app.include_router(draw.draw_day_router)
app.include_router(banking.router)
app.include_router(branch.router)
app.include_router(user.router)
