/** @type {import('@bacons/apple-targets/app.plugin').Config} */
module.exports = {
  type: "widget",
  name: "SyllogicWidget",
  icon: "../../assets/images/icon.png",
  entitlements: {
    "com.apple.security.application-groups": ["group.ai.syllogic.mobile"],
    "keychain-access-groups": ["$(AppIdentifierPrefix)ai.syllogic.mobile"],
  },
  deploymentTarget: "17.0",
  // NOTE: @bacons/apple-targets' Config type has no `infoPlist` key (see
  // node_modules/@bacons/apple-targets/build/config.d.ts) -- an `infoPlist`
  // block here would be silently discarded, not applied. SyllogicAPIBaseURL
  // lives directly in the committed `widget/Info.plist` instead; see the
  // comment there for why and how to change it.
};
