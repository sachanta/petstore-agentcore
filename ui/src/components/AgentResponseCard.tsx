import { Leaf } from "lucide-react";
import type { AgentResponse } from "../types";
import { StatusBadge } from "./StatusBadge";
import { ItemsTable } from "./ItemsTable";
import { FinancialSummary } from "./FinancialSummary";

export function AgentResponseCard({ response }: { response: AgentResponse }) {
  const hasItems    = (response.items?.length ?? 0) > 0;
  const hasSummary  = response.status === "Accept" && response.subtotal != null;
  const hasPetAdvice = response.petAdvice && response.petAdvice.trim().length > 0;

  return (
    <div className="rounded-2xl border border-gray-200 bg-white shadow-sm p-4 space-y-3 max-w-2xl">
      {/* Header */}
      <div className="flex items-center gap-2 flex-wrap">
        <StatusBadge status={response.status} />
        {response.customerType && (
          <span
            className={
              response.customerType === "Subscribed"
                ? "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium bg-brand-100 text-brand-700"
                : "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium bg-gray-100 text-gray-600"
            }
          >
            {response.customerType}
          </span>
        )}
      </div>

      {/* Message */}
      <p className="text-gray-800 text-sm leading-relaxed">{response.message}</p>

      {/* Items table */}
      {hasItems && <ItemsTable items={response.items!} />}

      {/* Financial summary */}
      {hasSummary && <FinancialSummary response={response} />}

      {/* Pet advice */}
      {hasPetAdvice && (
        <div className="flex gap-2 rounded-xl bg-brand-50 border border-brand-100 p-3">
          <Leaf size={16} className="mt-0.5 shrink-0 text-brand-600" />
          <p className="text-sm italic text-brand-800">{response.petAdvice}</p>
        </div>
      )}
    </div>
  );
}
