const CAMPAIGN = "oss_promotion";

function withUtm(
  rawUrl: string,
  content: string,
  source = "landing",
  medium = "site"
) {
  const url = new URL(rawUrl);
  url.searchParams.set("utm_source", source);
  url.searchParams.set("utm_medium", medium);
  url.searchParams.set("utm_campaign", CAMPAIGN);
  url.searchParams.set("utm_content", content);
  return url.toString();
}

export const LINKS = {
  repo: "https://github.com/syllogic-ai/syllogic",
  issues: "https://github.com/syllogic-ai/syllogic/issues",
  discussions: "https://github.com/syllogic-ai/syllogic/discussions",
  readme: "https://github.com/syllogic-ai/syllogic/blob/main/README.md",
  roadmap: "https://github.com/syllogic-ai/syllogic/blob/main/ROADMAP.md",
  contributing:
    "https://github.com/syllogic-ai/syllogic/blob/main/CONTRIBUTING.md",
  startHere:
    "https://github.com/syllogic-ai/syllogic/blob/main/START_HERE.md",
  release:
    "https://github.com/syllogic-ai/syllogic/releases/tag/v1.0.0",
  demo: {
    hero: withUtm(
      "https://app.syllogic.ai/login?demo=1",
      "hero_demo",
      "landing",
      "site"
    ),
    start: withUtm(
      "https://app.syllogic.ai/login?demo=1",
      "start_page_demo",
      "landing",
      "site"
    ),
    feedback: withUtm(
      "https://app.syllogic.ai/login?demo=1",
      "feedback_demo",
      "github",
      "issues"
    ),
  },
  railway: {
    hero: withUtm(
      "https://railway.com/deploy/N98lwA?referralCode=25KFsK",
      "hero_railway",
      "landing",
      "site"
    ),
    install: withUtm(
      "https://railway.com/deploy/N98lwA?referralCode=25KFsK",
      "install_railway",
      "landing",
      "site"
    ),
    readme: withUtm(
      "https://railway.com/deploy/N98lwA?referralCode=25KFsK",
      "readme_railway",
      "github",
      "readme"
    ),
  },
  issuesNew: {
    installHelp:
      "https://github.com/syllogic-ai/syllogic/issues/new?template=install_help.yml",
    demoFeedback:
      "https://github.com/syllogic-ai/syllogic/issues/new?template=demo_feedback.yml",
    featureRequest:
      "https://github.com/syllogic-ai/syllogic/issues/new?template=feature_request.yml",
  },
  startPath: "/start",
};

