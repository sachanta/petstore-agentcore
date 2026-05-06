import { AlertTriangle } from "lucide-react";
import type { OrderItem } from "../types";

export function ItemsTable({ items }: { items: OrderItem[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            {["Product", "Unit Price", "Qty", "Bundle Disc.", "Line Total", ""].map((h) => (
              <th
                key={h}
                className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-100">
          {items.map((item, i) => (
            <tr key={i}>
              <td className="px-3 py-2 font-mono text-gray-700">{item.productId}</td>
              <td className="px-3 py-2 text-gray-600">${item.price.toFixed(2)}</td>
              <td className="px-3 py-2 text-gray-600">{item.quantity}</td>
              <td className="px-3 py-2 text-gray-600">
                {item.bundleDiscount > 0 ? (
                  <span className="text-brand-700 font-medium">
                    {(item.bundleDiscount * 100).toFixed(0)}% off
                  </span>
                ) : (
                  <span className="text-gray-400">—</span>
                )}
              </td>
              <td className="px-3 py-2 font-medium text-gray-800">${item.total.toFixed(2)}</td>
              <td className="px-3 py-2">
                {item.replenishInventory && (
                  <span
                    title="Low stock — replenishment needed"
                    className="inline-flex items-center gap-1 text-xs text-amber-600 font-medium"
                  >
                    <AlertTriangle size={13} />
                    Reorder
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
