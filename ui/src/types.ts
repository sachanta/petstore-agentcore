export interface OrderItem {
  productId: string;
  price: number;
  quantity: number;
  bundleDiscount: number;
  total: number;
  replenishInventory: boolean;
}

export interface AgentResponse {
  status: "Accept" | "Reject" | "Error";
  message: string;
  customerType?: "Guest" | "Subscribed";
  items?: OrderItem[];
  shippingCost?: number;
  petAdvice?: string;
  subtotal?: number;
  additionalDiscount?: number;
  total?: number;
}

export type MessageRole = "user" | "agent";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  text?: string;
  response?: AgentResponse;
  loading?: boolean;
}
