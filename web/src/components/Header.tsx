import React, { useState } from 'react';
import { Search } from 'lucide-react';
import { IndexTicker, Security } from '../types';

interface HeaderProps {
  indices: IndexTicker[];
  securities: Security[];
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  colorScheme: 'CN' | 'INTL';
}

export const Header: React.FC<HeaderProps> = ({
  indices,
  securities,
  selectedSymbol,
  onSelectSymbol,
  colorScheme,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);

  const filteredSecurities = securities.filter(
    (s) =>
      s.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
      s.name.includes(searchTerm)
  );

  const getChangeColor = (val: number) => {
    if (val === 0) return 'text-warm-500';
    const isPositive = val > 0;
    if (colorScheme === 'CN') {
      return isPositive ? 'text-market-red' : 'text-market-green';
    } else {
      return isPositive ? 'text-market-green' : 'text-market-red';
    }
  };

  return (
    <header className="bg-white border-b border-warm-200 px-3 sm:px-4 lg:px-6 py-2 select-none">
      <div className="w-full max-w-[2560px] 2xl:max-w-[3400px] mx-auto flex items-center justify-between gap-3 sm:gap-4">
        {/* Brand */}
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-lg bg-warm-800 text-white flex items-center justify-center font-bold font-mono text-xs sm:text-sm tracking-tight shadow-xs">
            MIE
          </div>
          <div>
            <div className="text-xs sm:text-sm font-semibold text-warm-900 leading-tight tracking-tight flex items-center gap-1.5 sm:gap-2">
              <span>Market Insight Engine</span>
              <span className="text-[10px] font-mono px-1.5 py-0.2 bg-warm-100 text-warm-600 rounded border border-warm-200">
                v0.50
              </span>
            </div>
            <div className="text-[10px] sm:text-[11px] text-warm-500 font-sans hidden sm:block">
              量化数据服务与预测分析引擎
            </div>
          </div>
        </div>

        {/* Major Market Indices - Responsive Collapsing */}
        <div className="hidden lg:flex items-center gap-3 xl:gap-4 py-1 px-3 bg-warm-50 rounded-lg border border-warm-200 text-xs">
          {indices.map((idx, index) => (
            <div
              key={idx.symbol}
              className={`flex items-center gap-1.5 sm:gap-2 font-mono ${
                index >= 2 ? 'hidden 2xl:flex' : 'flex'
              }`}
            >
              <span className="text-warm-600 font-sans font-medium text-[11px] truncate max-w-[70px]">
                {idx.name}
              </span>
              <span className="font-semibold text-warm-800">{idx.price.toFixed(2)}</span>
              <span className={`text-[11px] font-medium ${getChangeColor(idx.pct_change)}`}>
                {idx.pct_change > 0 ? '+' : ''}{idx.pct_change.toFixed(2)}%
              </span>
            </div>
          ))}
        </div>

        {/* Search & Actions */}
        <div className="flex items-center gap-2.5 shrink-0">
          {/* Search Dropdown */}
          <div className="relative">
            <div className="relative flex items-center">
              <Search className="w-3.5 h-3.5 absolute left-2.5 text-warm-400 pointer-events-none" />
              <input
                type="text"
                placeholder="搜索代码或名称..."
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value);
                  setShowDropdown(true);
                }}
                onFocus={() => setShowDropdown(true)}
                className="w-36 sm:w-48 md:w-56 xl:w-64 pl-8 pr-3 py-1.5 text-xs bg-warm-50 hover:bg-white focus:bg-white border border-warm-200 focus:border-warm-400 rounded-md outline-none transition-colors font-mono"
              />
            </div>

            {showDropdown && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setShowDropdown(false)}
                />
                <div className="absolute right-0 mt-1 w-64 bg-white border border-warm-200 rounded-md shadow-lg z-50 max-h-60 overflow-y-auto py-1">
                  {filteredSecurities.length > 0 ? (
                    filteredSecurities.map((s) => (
                      <div
                        key={s.symbol}
                        onClick={() => {
                          onSelectSymbol(s.symbol);
                          setShowDropdown(false);
                          setSearchTerm('');
                        }}
                        className={`px-3 py-1.5 text-xs flex items-center justify-between cursor-pointer hover:bg-warm-100 ${
                          s.symbol === selectedSymbol ? 'bg-warm-50 font-semibold' : ''
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-warm-800">{s.symbol}</span>
                          <span className="text-warm-600">{s.name}</span>
                        </div>
                        <span className="text-[10px] text-warm-400 px-1 border border-warm-200 rounded uppercase">
                          {s.market}
                        </span>
                      </div>
                    ))
                  ) : (
                    <div className="px-3 py-2 text-xs text-warm-400 text-center">
                      未找到相关标的
                    </div>
                  )}
                </div>
              </>
            )}
          </div>

          {/* Engine Status Badge */}
          <div className="hidden sm:flex items-center gap-1.5 px-2 py-1 bg-warm-100 rounded-md text-[11px] font-mono text-warm-700 border border-warm-200 shrink-0">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            <span>API: 127.0.0.1</span>
          </div>
        </div>
      </div>
    </header>
  );
};
