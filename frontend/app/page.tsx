import { CustomerPane } from "@/components/customer/CustomerPane";
import { MerchantPane } from "@/components/merchant/MerchantPane";

// One page, two panes (docs/frontend.md). Panes share no client state: each talks to the backend.
export default function Home() {
  return (
    <main className="grid min-h-screen grid-cols-1 gap-3 bg-black p-3 lg:h-dvh lg:grid-rows-[minmax(0,1fr)] lg:overflow-hidden lg:grid-cols-[minmax(0,65fr)_minmax(340px,35fr)]">
      <MerchantPane />
      <CustomerPane />
    </main>
  );
}
