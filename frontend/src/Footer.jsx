import { useLang } from './i18n'

export default function Footer({ showUsage = false }) {
  const { t } = useLang()
  const email = window.__SUPPORT_EMAIL__ || ''

  if (!email && !showUsage) return null

  return (
    <footer className="text-center text-sm text-gray-500 py-4 px-4 border-t mt-8">
      {email && (
        <a href={`mailto:${email}`} className="text-blue-500 hover:underline">
          {t.footer_get_help}
        </a>
      )}
      {showUsage && (
        <span>
          {email && <span className="mx-2">·</span>}
          <a href="/usage" target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">
            {t.footer_usage}
          </a>
        </span>
      )}
    </footer>
  )
}
