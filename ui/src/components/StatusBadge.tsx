import { cva } from "class-variance-authority";
import type { AgentResponse } from "../types";

const badge = cva("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold", {
  variants: {
    status: {
      Accept: "bg-brand-100 text-brand-800",
      Reject: "bg-red-100 text-red-800",
      Error:  "bg-yellow-100 text-yellow-800",
    },
  },
});

export function StatusBadge({ status }: { status: AgentResponse["status"] }) {
  const label = status === "Accept" ? "✓ Accepted" : status === "Reject" ? "✗ Rejected" : "⚠ Error";
  return <span className={badge({ status })}>{label}</span>;
}
