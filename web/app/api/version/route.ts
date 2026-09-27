// The build this deployment serves. Open pages compare it with their own every 5 minutes.
export const dynamic = "force-dynamic"

export function GET() {
  return Response.json(
    { build: process.env.NEXT_PUBLIC_BUILD_ID ?? "dev" },
    { headers: { "Cache-Control": "no-store" } },
  )
}
