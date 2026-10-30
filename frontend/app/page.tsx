import { CustomerPane } from "@/components/customer/CustomerPane";
import { MerchantPane } from "@/components/merchant/MerchantPane";

// One page, two panes (docs/frontend.md). Panes share no client state: each talks to the backend.
export default function Home() {
  return (
    <main className="grid h-screen min-w-[1280px] grid-cols-[65fr_35fr]">
      <MerchantPane />
      <CustomerPane />
    </main>
  );
}
