document.addEventListener('DOMContentLoaded', () => {
    const filterInput = document.getElementById('filter-input');
    const itemsList = document.getElementById('items-list');

    if (filterInput && itemsList) {
        const items = itemsList.querySelectorAll('.item');
        filterInput.addEventListener('input', function () {
            const query = this.value.toLowerCase().trim();

            items.forEach(item => {
                const name = item.dataset.name;
                if (name.includes(query)) {
                    item.classList.remove('hidden');
                } else {
                    item.classList.add('hidden');
                }
            });
        });
    }
});
