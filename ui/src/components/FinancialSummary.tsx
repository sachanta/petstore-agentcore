import type { AgentResponse } from "../types";

export function FinancialSummary({ response }: { response: AgentResponse }) {
  const { subtotal = 0, additionalDiscount = 0, shippingCost = 0, total = 0 } = response;

  return (
    <div className="ml-auto w-56 space-y-1 text-sm">
      <Row label="Subtotal" value={`$${subtotal.toFixed(2)}`} />
      {additionalDiscount > 0 && (
        <Row
          label={`Discount (${(additionalDiscount * 100).toFixed(0)}%)`}
          value={`−$${(subtotal * additionalDiscount).toFixed(2)}`}
          className="text-red-600"
        />
      )}
      <Row
        label="Shipping"
        value={shippingCost === 0 ? "FREE" : `$${shippingCost.toFixed(2)}`}
        className={shippingCost === 0 ? "text-brand-600 font-medium" : ""}
      />
      <div className="border-t border-gray-200 pt-1 flex justify-between font-bold text-gray-900">
        <span>Total</span>
        <span>${total.toFixed(2)}</span>
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  className = "",
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div className="flex justify-between text-gray-600">
      <span>{label}</span>
      <span className={className}>{value}</span>
    </div>
  );
}
