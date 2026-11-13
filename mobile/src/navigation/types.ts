import type { Product, PriceAlert } from '../api/types';
export type RootStackParams = {
  Main: undefined;
  Product: { product: Product };
  Auth: { register?: boolean } | undefined;
  AlertForm: { product?: string; alert?: PriceAlert } | undefined;
  Profile: undefined;
  Connection: undefined;
};
export type TabParams = { Offers: undefined; Alerts: undefined; Notifications: undefined; Account: undefined };
