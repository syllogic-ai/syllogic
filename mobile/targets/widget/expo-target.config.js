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
  infoPlist: {
    SyllogicAPIBaseURL: process.env.EXPO_PUBLIC_API_URL || "http://localhost:8000",
  },
};
