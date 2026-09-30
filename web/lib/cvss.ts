// CVSS 3.x base vector: "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H".

export const BASE_METRICS = ["AV", "AC", "PR", "UI", "S", "C", "I", "A"] as const
export type BaseMetric = (typeof BASE_METRICS)[number]

const NAMES: Record<BaseMetric, Record<string, string>> = {
  AV: { N: "Network", A: "Adjacent", L: "Local", P: "Physical" },
  AC: { L: "Low", H: "High" },
  PR: { N: "None", L: "Low", H: "High" },
  UI: { N: "None", R: "Required" },
  S: { U: "Unchanged", C: "Changed" },
  C: { N: "None", L: "Low", H: "High" },
  I: { N: "None", L: "Low", H: "High" },
  A: { N: "None", L: "Low", H: "High" },
}

export const IMPACT_METRICS: ReadonlySet<BaseMetric> = new Set(["C", "I", "A"])

export interface VectorChip {
  metric: BaseMetric
  value: string | null // "N", or null when the vector is unknown
  label: string | null // "Network"
}

export function parseVector(vector: string | null): VectorChip[] {
  const parts = new Map<string, string>()
  for (const part of vector?.split("/") ?? []) {
    const [k, v] = part.split(":")
    if (k && v) parts.set(k, v)
  }
  return BASE_METRICS.map((metric) => {
    const value = parts.get(metric) ?? null
    return { metric, value, label: value ? (NAMES[metric][value] ?? value) : null }
  })
}

/** One plain-English line from the NVD vector, built in code (no model): "Remote, no auth, no
 * user interaction". Attack complexity only when high. Null without an attack vector. */
export function plainVector(vector: string | null): string | null {
  const v = new Map(parseVector(vector).map((c) => [c.metric, c.value]))
  const where = { N: "Remote", A: "Adjacent network", L: "Local access", P: "Physical access" }[v.get("AV") ?? ""]
  if (!where) return null
  const parts = [where]
  if (v.get("AC") === "H") parts.push("hard to exploit")
  const auth = { N: "no auth", L: "low-privilege account", H: "admin account" }[v.get("PR") ?? ""]
  if (auth) parts.push(auth)
  const user = { N: "no user interaction", R: "needs user interaction" }[v.get("UI") ?? ""]
  if (user) parts.push(user)
  return parts.join(", ")
}
