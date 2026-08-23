Pod::Spec.new do |s|
  s.name           = 'WidgetReload'
  s.version        = '1.0.0'
  s.summary        = 'Native bridge for requesting a WidgetKit timeline reload from the app.'
  s.description    = 'Wraps WidgetCenter.shared.reloadAllTimelines() so the Expo app can ask iOS home screen widgets to refresh their data after sign-in and settings changes.'
  s.author         = ''
  s.homepage       = 'https://docs.expo.dev/modules/'
  s.platforms      = {
    :ios => '16.4',
    :tvos => '16.4'
  }
  s.source         = { git: '' }
  s.static_framework = true

  s.dependency 'ExpoModulesCore'

  # Swift/Objective-C compatibility
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
  }

  s.source_files = "**/*.{h,m,mm,swift,hpp,cpp}"
end
