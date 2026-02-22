const { chromium } = require('playwright');
const TelegramBot = require('node-telegram-bot-api');
const fs = require('fs');

const TOKEN = '8596594907:AAHUQjk-ik3LGV7kI-4XhCn-fw1T-FHo6wU';
const CHAT = '-1003179573402';
const URL = 'https://1xlite-7636770.bar/ru/live/baccarat';
const LAST_NUMBER_FILE = './last_number.txt';

const bot = new TelegramBot(TOKEN, { polling: false });

let lastMessageId = null;
let lastMessageText = '';

// Загружаем последний номер из файла (на всякий случай)
let lastGameNumber = '0';
if (fs.existsSync(LAST_NUMBER_FILE)) {
    lastGameNumber = fs.readFileSync(LAST_NUMBER_FILE, 'utf8');
    console.log('Загружен последний номер:', lastGameNumber);
}

function formatCards(cards) {
    return cards.join('');
}

function determineTurn(playerCards, bankerCards) {
    if (playerCards.length === 2 && bankerCards.length === 2) return 'player';
    if (playerCards.length === 3 && bankerCards.length === 2) return 'banker';
    if (playerCards.length === 2 && bankerCards.length === 3) return 'player';
    return null;
}

// Номер игры по московскому времени (старт в 3:00)
function getGameNumberByTime() {
    const now = new Date();
    
    // Переводим в московское время (UTC+3)
    const mskTime = new Date(now.toLocaleString('en-US', { timeZone: 'Europe/Moscow' }));
    
    const currentHours = mskTime.getHours();
    const currentMinutes = mskTime.getMinutes();
    
    // Начало отсчета: 3:00 МСК
    const startHour = 3;
    const startMinute = 0;
    
    // Если сейчас меньше 3:00, значит игры еще не начались
    if (currentHours < startHour || (currentHours === startHour && currentMinutes < startMinute)) {
        return null;
    }
    
    // Считаем сколько минут прошло с 3:00
    const minutesSinceStart = (currentHours - startHour) * 60 + (currentMinutes - startMinute);
    
    // Номер игры = минуты с начала + 1
    return minutesSinceStart + 1;
}

async function sendOrEditTelegram(newMessage) {
    if (!newMessage || newMessage === lastMessageText) return;
    
    try {
        if (lastMessageId) {
            await bot.editMessageText(newMessage, {
                chat_id: CHAT,
                message_id: lastMessageId
            });
        } else {
            const msg = await bot.sendMessage(CHAT, newMessage);
            lastMessageId = msg.message_id;
        }
        lastMessageText = newMessage;
    } catch (e) {
        console.log('TG error:', e.message);
    }
}

// Поиск первого активного стола
async function findFirstLiveGame(page) {
    const games = await page.$$('.dashboard-game');
    for (const game of games) {
        const hasTimer = await game.$('.dashboard-game-info__time') !== null;
        if (!hasTimer) continue;

        const isFinished = await game.evaluate(el => {
            const period = el.querySelector('.dashboard-game-info__period');
            return period?.textContent.includes('Игра завершена') ?? false;
        });

        if (!isFinished) {
            const link = await game.$('a[href*="/ru/live/baccarat/"]');
            if (link) return await link.getAttribute('href');
        }
    }
    return null;
}

async function getCards(page) {
    const playerBlock = await page.$('.baccarat-player:not(.baccarat-player--is-reversed) .baccarat-player__cards');
    const player = playerBlock ? await playerBlock.$$eval('li.baccarat-player__card-box', cards => {
        return cards.map(c => {
            const rankEl = c.querySelector('.baccarat-card__rank');
            if (!rankEl) return null;
            const rank = rankEl.textContent.trim();
            const suitIcon = c.querySelector('.baccarat-card__suit');
            let suit = '';
            if (suitIcon) {
                if (suitIcon.className.includes('spades')) suit = '♠️';
                else if (suitIcon.className.includes('hearts')) suit = '♥️';
                else if (suitIcon.className.includes('clubs')) suit = '♣️';
                else if (suitIcon.className.includes('diamonds')) suit = '♦️';
            }
            return rank + suit;
        }).filter(c => c !== null).slice(0, 3);
    }) : [];

    const bankerBlock = await page.$('.baccarat-player--is-reversed .baccarat-player__cards');
    const banker = bankerBlock ? await bankerBlock.$$eval('li.baccarat-player__card-box', cards => {
        return cards.map(c => {
            const rankEl = c.querySelector('.baccarat-card__rank');
            if (!rankEl) return null;
            const rank = rankEl.textContent.trim();
            const suitIcon = c.querySelector('.baccarat-card__suit');
            let suit = '';
            if (suitIcon) {
                if (suitIcon.className.includes('spades')) suit = '♠️';
                else if (suitIcon.className.includes('hearts')) suit = '♥️';
                else if (suitIcon.className.includes('clubs')) suit = '♣️';
                else if (suitIcon.className.includes('diamonds')) suit = '♦️';
            }
            return rank + suit;
        }).filter(c => c !== null).slice(0, 3);
    }) : [];

    const pScore = await page.$eval('.baccarat-player:not(.baccarat-player--is-reversed) .baccarat-player__number', el => el.textContent).catch(() => '0');
    const bScore = await page.$eval('.baccarat-player--is-reversed .baccarat-player__number', el => el.textContent).catch(() => '0');

    return { player, banker, pScore, bScore };
}

async function monitorGame(page, gameNumber) {
    let lastCards = { player: [], banker: [], pScore: '0', bScore: '0' };
    
    while (true) {
        const cards = await getCards(page);
        
        // Проверка на завершение игры через селектор
        const isGameOver = await page.evaluate(() => {
            const panel = document.querySelector('.market-grid__game-over-panel');
            if (!panel) return false;
            const caption = panel.querySelector('.ui-caption');
            return caption && caption.textContent.includes('Игра завершена');
        });
        
        if (isGameOver) {
            const cards = await getCards(page);
            
            if (cards.player.length > 0 || cards.banker.length > 0) {
                console.log('Игра завершена, отправляю результат...');
                
                const total = parseInt(cards.pScore) + parseInt(cards.bScore);
                const winner = cards.pScore > cards.bScore ? 'П1' : (cards.bScore > cards.pScore ? 'П2' : 'X');
                const noDrawFlag = cards.player.length === 2 && cards.banker.length === 2 ? '#R ' : '';
                
                let message;
                if (cards.pScore > cards.bScore) {
                    message = `#N${gameNumber} ✅${cards.pScore} (${formatCards(cards.player)}) - ${cards.bScore} (${formatCards(cards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
                } else if (cards.bScore > cards.pScore) {
                    message = `#N${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) - ✅${cards.bScore} (${formatCards(cards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
                } else {
                    message = `#N${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) 🔰 ${cards.bScore} (${formatCards(cards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
                }
                
                await sendOrEditTelegram(message);
            }
            
            console.log('Жду 10 секунд перед закрытием...');
            await page.waitForTimeout(10000);
            break;
        }
        
        if (cards.player.length > 0 && cards.banker.length > 0) {
            const turn = determineTurn(cards.player, cards.banker);
            
            let message;
            if (turn === 'player') {
                message = `⏱№${gameNumber} 👉${cards.pScore}(${formatCards(cards.player)}) -${cards.bScore} (${formatCards(cards.banker)})`;
            } else if (turn === 'banker') {
                message = `⏱№${gameNumber} ${cards.pScore}(${formatCards(cards.player)}) -👉${cards.bScore} (${formatCards(cards.banker)})`;
            } else {
                message = `⏱№${gameNumber} ${cards.pScore}(${formatCards(cards.player)}) -${cards.bScore} (${formatCards(cards.banker)})`;
            }
            
            const cardsChanged = 
                JSON.stringify(cards.player) !== JSON.stringify(lastCards.player) ||
                JSON.stringify(cards.banker) !== JSON.stringify(lastCards.banker) ||
                cards.pScore !== lastCards.pScore ||
                cards.bScore !== lastCards.bScore;
            
            if (cardsChanged) {
                await sendOrEditTelegram(message);
                lastCards = { ...cards };
            }
        }
        
        await page.waitForTimeout(2000);
    }
}

async function run() {
    let browser;
    let timeout;
    
    try {
        const startTime = new Date();
        console.log(`\n🟢 Браузер открыт в ${startTime.toLocaleTimeString()}.${startTime.getMilliseconds()}`);
        
        browser = await chromium.launch({ headless: true });
        const page = await browser.newPage();
        
        // Таймаут 2 минуты
        timeout = setTimeout(async () => {
            console.log(`⏱ 2 минуты прошло, закрываю браузер`);
            if (browser) await browser.close();
        }, 120000);
        
        await page.goto(URL);
        console.log('Ищем активный стол...');
        
        let activeLink = null;
        let attempts = 0;
        while (!activeLink && attempts < 10) {
            activeLink = await findFirstLiveGame(page);
            if (!activeLink) {
                console.log('Жду 5 секунд...');
                await page.waitForTimeout(5000);
                attempts++;
            }
        }
        
        if (!activeLink) {
            console.log('❌ Не нашел активный стол за 10 попыток');
            return;
        }
        
        console.log('Захожу в стол:', activeLink);
        await page.click(`a[href="${activeLink}"]`);
        await page.waitForTimeout(3000);
        
        // ПОЛУЧАЕМ НОМЕР ПО МОСКОВСКОМУ ВРЕМЕНИ
        let gameNumber = getGameNumberByTime();
        
        if (!gameNumber) {
            console.log('⏰ До начала игр еще время (старт в 3:00 МСК)');
            return;
        }
        
        console.log('🎰 Номер игры по времени (МСК):', gameNumber);
        gameNumber = gameNumber.toString();
        
        // Сохраняем номер в файл (на всякий случай)
        lastGameNumber = gameNumber;
        fs.writeFileSync(LAST_NUMBER_FILE, gameNumber);
        
        let attemptsCards = 0;
        let cards = { player: [], banker: [] };
        while (attemptsCards < 12 && (cards.player.length === 0 || cards.banker.length === 0)) {
            await page.waitForTimeout(5000);
            cards = await getCards(page);
            attemptsCards++;
        }
        
        if (cards.player.length > 0 && cards.banker.length > 0) {
            await monitorGame(page, gameNumber);
        }
        
    } catch (e) {
        console.log('Ошибка:', e.message);
    } finally {
        if (timeout) clearTimeout(timeout);
        if (browser) {
            await browser.close();
            lastMessageId = null;
            lastMessageText = '';
        }
    }
}

// Функция для расчета задержки до запуска браузера в :02 секунд
function getDelayToNextGame() {
    const now = new Date();
    const seconds = now.getSeconds();
    const milliseconds = now.getMilliseconds();
    const targetSeconds = 2;
    
    let delaySeconds;
    if (seconds < targetSeconds) {
        delaySeconds = targetSeconds - seconds;
    } else {
        delaySeconds = (60 - seconds) + targetSeconds;
    }
    
    return (delaySeconds * 1000) - milliseconds;
}

// Запуск с интервалом 35 секунд
(async () => {
    console.log('🤖 Бот Baccarat запущен');
    console.log('🎯 Номера игр по московскому времени (3:00 = #1)');
    console.log('⏱ Время жизни браузера: 2 минуты');
    console.log('⏱ Интервал запуска: 35 секунд');
    
    // Синхронизация с ближайшей игрой
    const initialDelay = getDelayToNextGame();
    const nextRunTime = new Date(Date.now() + initialDelay);
    console.log(`⏱ Синхронизация: первый запуск через ${(initialDelay/1000).toFixed(3)} секунд`);
    console.log(`⏱ Время первого запуска: ${nextRunTime.toLocaleTimeString()}.${nextRunTime.getMilliseconds()}`);
    
    await new Promise(resolve => setTimeout(resolve, initialDelay));
    console.log('✅ Синхронизировались!');
    
    while (true) {
        const now = new Date();
        console.log(`\n🚀 Запуск браузера в ${now.toLocaleTimeString()}.${now.getMilliseconds()}`);
        
        run(); // не ждем завершения
        
        await new Promise(resolve => setTimeout(resolve, 35000)); // 35 секунд
    }
})();
