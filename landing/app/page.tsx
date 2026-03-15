import { SideNav } from "@/components/side-nav";
import { HeroSection } from "@/components/hero-section";
import { SignalsSection } from "@/components/signals-section";
import { PreviewSection } from "@/components/preview-section";
import { WhySection } from "@/components/why-section";
import { WorkSection } from "@/components/work-section";
import { PrinciplesSection } from "@/components/principles-section";
import { RoadmapSection } from "@/components/roadmap-section";
import { ColophonSection } from "@/components/colophon-section";
import { AuthorsSection } from "@/components/authors-section";

export default function Home() {
  return (
    <main>
      <SideNav />
      <HeroSection />
      <SignalsSection />
      <PreviewSection />
      <WhySection />
      <WorkSection />
      <PrinciplesSection />
      <RoadmapSection />
      <ColophonSection />
      <AuthorsSection />
    </main>
  );
}
