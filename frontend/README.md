# frontend

React + Vite frontend for Xiyangyang Clock.

## Stack

- React
- TypeScript
- Vite
- shadcn/ui compatible project structure
- FullCalendar
- Tailwind CSS

## Environment

Copy `.env.example` to `.env` for local development.

```powershell
Copy-Item .env.example .env
```

Required variables:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
```

## Local Development

```powershell
npm install
npm run dev
```

Build check:

```powershell
npm run build
```
