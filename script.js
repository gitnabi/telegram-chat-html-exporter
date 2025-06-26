// Современный упрощенный JavaScript с использованием History API

document.addEventListener('DOMContentLoaded', () => {
    initializeNavigation();
    setupLazyLoading();
    handleInitialNavigation();
    initializeCodeHighlighting();
});

// Инициализация навигации
function initializeNavigation() {
    // Обработчики кликов по табам
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', (e) => {
            e.preventDefault();
            const topicId = tab.dataset.id;
            navigateToTopic(topicId);
        });
    });
    
    // Обработка навигации браузера (кнопки назад/вперед)
    window.addEventListener('popstate', handleNavigation);
}

// Навигация к топику
function navigateToTopic(topicId, updateHistory = true) {
    // Обновляем активные табы
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.toggle('bg-github-hover', tab.dataset.id === topicId);
        tab.classList.toggle('border-github-accent', tab.dataset.id === topicId);
    });
    
    // Показываем нужную секцию
    document.querySelectorAll('section[id^="topic-"]').forEach(section => {
        if (section.id === `topic-${topicId}`) {
            section.classList.remove('section-hidden');
        } else {
            section.classList.add('section-hidden');
        }
    });
    
    // Обновляем URL без перезагрузки страницы
    if (updateHistory) {
        const newUrl = topicId === '1' ? 
            window.location.pathname : 
            `${window.location.pathname}#topic-${topicId}`;
        history.pushState({ topicId }, '', newUrl);
    }
    
    // Плавная прокрутка наверх
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Обработка навигации (включая хэш-ссылки на сообщения)
function handleNavigation() {
    const hash = window.location.hash;
    
    if (hash.startsWith('#msg-')) {
        // Навигация к конкретному сообщению
        handleMessageNavigation(hash);
    } else if (hash.startsWith('#topic-')) {
        // Навигация к топику
        const topicId = hash.replace('#topic-', '');
        navigateToTopic(topicId, false);
    } else {
        // Показываем первый топик по умолчанию
        const firstTab = document.querySelector('.tab');
        if (firstTab) {
            navigateToTopic(firstTab.dataset.id, false);
        }
    }
}

// Навигация к конкретному сообщению
function handleMessageNavigation(hash) {
    const msgId = hash.replace('#msg-', '');
    const msgElement = document.getElementById(`msg-${msgId}`);
    
    if (msgElement) {
        // Находим топик, содержащий это сообщение
        const section = msgElement.closest('section');
        if (section) {
            const topicId = section.id.replace('topic-', '');
            
            // Переключаемся на нужный топик
            navigateToTopic(topicId, false);
            
            // Прокручиваем к сообщению с небольшой задержкой
            setTimeout(() => {
                msgElement.scrollIntoView({ 
                    behavior: 'smooth', 
                    block: 'center' 
                });
                
                // Добавляем визуальное выделение
                msgElement.style.boxShadow = '0 0 0 2px #58a6ff';
                setTimeout(() => {
                    msgElement.style.boxShadow = '';
                }, 3000);
            }, 100);
        }
    }
}

// Обработка начальной навигации при загрузке страницы
function handleInitialNavigation() {
    if (window.location.hash) {
        handleNavigation();
    } else {
        // Показываем первый топик по умолчанию
        const firstTab = document.querySelector('.tab');
        if (firstTab) {
            navigateToTopic(firstTab.dataset.id, false);
        }
    }
}

// Настройка ленивой загрузки изображений
function setupLazyLoading() {
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    
                    // Убираем наблюдение за этим элементом
                    observer.unobserve(img);
                    
                    // Добавляем плавное появление только если изображение еще не загружено
                    if (!img.complete) {
                        img.style.opacity = '0';
                        img.style.transition = 'opacity 0.3s ease';
                        
                        const handleLoad = () => {
                            img.style.opacity = '1';
                            img.removeEventListener('load', handleLoad);
                            img.removeEventListener('error', handleLoad);
                        };
                        
                        img.addEventListener('load', handleLoad);
                        img.addEventListener('error', handleLoad);
                        
                        // Если изображение уже в кэше, сразу показываем
                        if (img.complete) {
                            handleLoad();
                        }
                    }
                }
            });
        }, {
            rootMargin: '50px 0px', // Начинаем загрузку за 50px до появления
            threshold: 0.1
        });
        
        // Наблюдаем за всеми изображениями с lazy loading
        document.querySelectorAll('img[loading="lazy"]').forEach(img => {
            // Если изображение уже загружено, не добавляем его в наблюдение
            if (img.complete && img.naturalHeight !== 0) {
                return;
            }
            imageObserver.observe(img);
        });
    }
}

// Дополнительные утилиты для улучшения UX
document.addEventListener('keydown', (e) => {
    // Навигация с клавиатуры (стрелки влево/вправо для переключения топиков)
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        const tabs = Array.from(document.querySelectorAll('.tab'));
        const activeTab = document.querySelector('.tab.bg-github-hover');
        
        if (activeTab) {
            const currentIndex = tabs.indexOf(activeTab);
            let newIndex;
            
            if (e.key === 'ArrowLeft') {
                newIndex = currentIndex > 0 ? currentIndex - 1 : tabs.length - 1;
            } else {
                newIndex = currentIndex < tabs.length - 1 ? currentIndex + 1 : 0;
            }
            
            navigateToTopic(tabs[newIndex].dataset.id);
        }
    }
});

// Улучшенная обработка внутренних ссылок
document.addEventListener('click', (e) => {
    const link = e.target.closest('a.internal-link');
    if (link) {
        e.preventDefault();
        const href = link.getAttribute('href');
        if (href && href.startsWith('#msg-')) {
            // Обновляем URL и обрабатываем навигацию
            history.pushState(null, '', href);
            handleMessageNavigation(href);
        }
    }
});

// Инициализация подсветки синтаксиса
function initializeCodeHighlighting() {
    // Проверяем, что Highlight.js загружен
    if (typeof hljs === 'undefined') {
        console.warn('Highlight.js не загружен');
        return;
    }

    // Обрабатываем все блоки кода
    document.querySelectorAll('pre code').forEach(block => {
        enhanceCodeBlock(block);
    });
}

// Улучшение блока кода с подсветкой синтаксиса и номерами строк
function enhanceCodeBlock(codeElement) {
    const preElement = codeElement.parentElement;
    
    // Пропускаем уже обработанные блоки
    if (preElement.classList.contains('hljs-processed')) {
        return;
    }
    
    // Получаем текст кода
    const codeText = codeElement.textContent || codeElement.innerText;
    
    // Получаем язык из атрибута class элемента code
    const language = getLanguageFromClass(codeElement);
    
    // Применяем подсветку синтаксиса
    let highlightedCode;
    if (language && hljs.getLanguage(language)) {
        try {
            highlightedCode = hljs.highlight(codeText, { language }).value;
        } catch (e) {
            console.warn('Ошибка подсветки синтаксиса:', e);
            highlightedCode = hljs.highlightAuto(codeText).value;
        }
    } else {
        highlightedCode = hljs.highlightAuto(codeText).value;
    }
    
    // Создаем структуру с номерами строк
    const lines = codeText.split('\n');
    const lineNumbers = lines.map((_, index) => index + 1).join('\n');
    
    // Создаем новую структуру
    const wrapper = document.createElement('div');
    wrapper.className = 'code-block-with-lines';
    
    const newPre = document.createElement('pre');
    newPre.className = 'hljs-processed';
    
    const lineNumbersDiv = document.createElement('div');
    lineNumbersDiv.className = 'code-line-numbers';
    lineNumbersDiv.textContent = lineNumbers;
    
    const codeContentDiv = document.createElement('div');
    codeContentDiv.className = 'code-content';
    
    const newCode = document.createElement('code');
    newCode.className = language ? `language-${language}` : '';
    newCode.innerHTML = highlightedCode;
    
    // Собираем структуру
    codeContentDiv.appendChild(newCode);
    newPre.appendChild(lineNumbersDiv);
    newPre.appendChild(codeContentDiv);
    wrapper.appendChild(newPre);
    
    // Заменяем оригинальный элемент
    preElement.parentNode.replaceChild(wrapper, preElement);
}

// Извлечение языка программирования из атрибута class
function getLanguageFromClass(codeElement) {
    const classList = codeElement.classList;
    
    // Ищем класс вида 'language-*'
    for (const className of classList) {
        if (className.startsWith('language-')) {
            return className.replace('language-', '');
        }
    }
    
    // Если язык не найден в классах, возвращаем null для автоопределения
    return null;
}
