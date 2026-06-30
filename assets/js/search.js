document.addEventListener('DOMContentLoaded', () => {
    if (typeof searchData === 'undefined') return;

    const searchInput = document.getElementById('search-input');
    const searchDropdown = document.getElementById('search-dropdown');

    if (searchInput && searchDropdown) {
        searchInput.addEventListener('input', function () {
            const query = this.value.toLowerCase().trim();

            if (query.length < 2) {
                searchDropdown.classList.add('hidden');
                return;
            }

            // Split query into parts for wildcard matching
            const queryParts = query.split(/[.\s]+/).filter(p => p.length > 0);

            const results = searchData.filter(item => {
                const searchNameLower = item.searchName;
                const descLower = item.desc.toLowerCase();

                // Check if ALL query parts match somewhere in searchName or desc
                return queryParts.every(part =>
                    searchNameLower.includes(part) || descLower.includes(part)
                );
            });

            // Sort: methods first, then types, then constructors
            // Within each category, prioritize name matches over desc matches
            results.sort((a, b) => {
                const typeOrder = { 'method': 0, 'type': 1, 'constructor': 2 };
                const aOrder = typeOrder[a.type] ?? 3;
                const bOrder = typeOrder[b.type] ?? 3;

                // First sort by type (methods first)
                if (aOrder !== bOrder) return aOrder - bOrder;

                // Then prioritize name matches within same type
                const aNameMatch = queryParts.some(p => a.searchName.includes(p));
                const bNameMatch = queryParts.some(p => b.searchName.includes(p));
                if (aNameMatch && !bNameMatch) return -1;
                if (!aNameMatch && bNameMatch) return 1;

                return 0;
            });

            const methodResults = results.filter(r => r.type === 'method');
            const typeResults = results.filter(r => r.type === 'type');
            const constructorResults = results.filter(r => r.type === 'constructor');
            const limitedResults = [...methodResults, ...typeResults, ...constructorResults];

            // Use rootPath global variable if available, otherwise default to current
            const root = typeof rootPath !== 'undefined' ? rootPath : '.';

            if (limitedResults.length === 0) {
                searchDropdown.innerHTML = '<div style="padding: 12px 16px; color: var(--text-secondary);">No results found</div>';
            } else {
                searchDropdown.innerHTML = limitedResults.map(item => `
                    <a href="${root}/${item.path}" class="search-item">
                        <span class="search-item-name">${item.goDisplay}</span>
                        <span class="search-item-type ${item.type}">${item.type}</span>
                    </a>
                `).join('');
            }
            searchDropdown.classList.remove('hidden');
        });

        document.addEventListener('click', function (e) {
            if (!searchInput.contains(e.target) && !searchDropdown.contains(e.target)) {
                searchDropdown.classList.add('hidden');
            }
        });

        searchInput.addEventListener('focus', function () {
            if (this.value.length >= 2) {
                searchDropdown.classList.remove('hidden');
            }
        });
    }
});
