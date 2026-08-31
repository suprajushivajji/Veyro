export default function Home() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="container mx-auto px-4 py-16">
        <div className="text-center">
          <h1 className="text-6xl font-bold text-gray-900 mb-4">
            RecoverOS
          </h1>
          <p className="text-xl text-gray-600 mb-8">
            AI Revenue Recovery Portfolio Optimizer
          </p>
          <div className="bg-white rounded-lg shadow-lg p-8 max-w-2xl mx-auto">
            <h2 className="text-2xl font-semibold text-gray-800 mb-4">
              Welcome to RecoverOS
            </h2>
            <p className="text-gray-600 mb-6">
              Intelligent revenue recovery system powered by AI to optimize your portfolio and recover lost revenue.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-8">
              <div className="bg-blue-50 rounded-lg p-4">
                <div className="text-3xl mb-2">🔍</div>
                <h3 className="font-semibold text-gray-800">Detect</h3>
                <p className="text-sm text-gray-600">Identify revenue patterns</p>
              </div>
              <div className="bg-green-50 rounded-lg p-4">
                <div className="text-3xl mb-2">🤖</div>
                <h3 className="font-semibold text-gray-800">Optimize</h3>
                <p className="text-sm text-gray-600">AI-powered decisions</p>
              </div>
              <div className="bg-purple-50 rounded-lg p-4">
                <div className="text-3xl mb-2">💰</div>
                <h3 className="font-semibold text-gray-800">Recover</h3>
                <p className="text-sm text-gray-600">Maximize revenue</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  )
}
