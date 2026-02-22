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
let lastGameNumber = '0';

if (fs.existsSync(LAST_NUMBER_FILE)) {
    lastGameNumber = fs.readFileSync(LAST_NUMBER_FILE, 'utf8');
    console.log('Загружен последний номер:', lastGameNumber);
}

function formatCards(cards) {
    return cards.join('');
}

function determineWinner(playerScore, bankerScore) {
    if (playerScore > bankerScore) return 'П1';
    if (bankerScore > playerScore) return 'П2';
    return 'X';
}

function getCardCountColor(playerCount, bankerCount) {
    return `#C${playerCount}_${bankerCount}`;
}

// Проверка на натуральную победу (7-9 очков с двух карт)
function isNaturalWin(score, cardCount) {
    return cardCount === 2 && (score >= 7 && score <= 9);
}

// Определение флага раздачи #R🔵
function getNaturalFlag(playerScore, playerCount, bankerScore, bankerCount) {
    // Если у кого-то натуральные 7-9 с двух карт
    if (playerCount === 2 && bankerCount === 2) {
        if ((playerScore >= 7 && playerScore <= 9) || (bankerScore >= 7 && bankerScore <= 9)) {
            return ' #R🔵';
        }
    }
    return '';
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

// Поиск первого стола с таймером
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
    let gameOverCount = 0; // Счетчик для проверки ложных срабатываний

    while (true) {
        const cards = await getCards(page);

        // Проверка на завершение игры через селектор market-grid__game-over-panel
        const isGameOver = await page.evaluate(() => {
            const panel = document.querySelector('.market-grid__game-over-panel');
            if (!panel) return false;
            
            // Дополнительно проверяем, есть ли текст "Игра завершена"
            const caption = panel.querySelector('.ui-caption');
            return caption && caption.textContent.includes('Игра завершена');
        });

        if (isGameOver) {
            gameOverCount++;
            console.log(`⚠️ Обнаружен game-over панель (попытка ${gameOverCount}/3)`);
            
            // Проверяем 3 раза с интервалом, чтобы убедиться, что это не ложное срабатывание
            if (gameOverCount >= 3) {
                console.log(`🏁 Игра #${gameNumber} действительно завершена, закрываю браузер`);
                return true; // Сигнал о завершении
            }
            await page.waitForTimeout(1000);
            continue;
        } else {
            gameOverCount = 0; // Сбрасываем счетчик, если панель исчезла
        }

        // Проверка на завершение через dashboard-game-info__period
        const isFinished = await page.evaluate(() => {
            const el = document.querySelector('.dashboard-game-info__period');
            return el && el.textContent.includes('Игра завершена');
        });

        if (isFinished) {
            const total = parseInt(cards.pScore) + parseInt(cards.bScore);
            const winner = determineWinner(parseInt(cards.pScore), parseInt(cards.bScore));
            const cardCountColor = getCardCountColor(cards.player.length, cards.banker.length);
            const naturalFlag = getNaturalFlag(
                parseInt(cards.pScore), cards.player.length,
                parseInt(cards.bScore), cards.banker.length
            );
            
            let message;
            if (winner === 'П1') {
                message = `#N${gameNumber} ✅${cards.pScore} (${formatCards(cards.player)}) - ${cards.bScore} (${formatCards(cards.banker)})${naturalFlag} #${winner} #T${total} ${cardCountColor}`;
            } else if (winner === 'П2') {
                message = `#N${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) - ✅${cards.bScore} (${formatCards(cards.banker)})${naturalFlag} #${winner} #T${total} ${cardCountColor}`;
            } else {
                message = `#N${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) 🔰 ${cards.bScore} (${formatCards(cards.banker)})${naturalFlag} #${winner} #T${total} ${cardCountColor}`;
            }

            await sendOrEditTelegram(message);
            console.log(`✅ Игра #${gameNumber} завершена`);
            return true; // Сигнал о завершении
        }

        if (cards.player.length > 0 && cards.banker.length > 0) {
            let message;
            const playerScore = parseInt(cards.pScore);
            const bankerScore = parseInt(cards.bScore);
            
            // ПРОВЕРКА НА НАТУРАЛЬНУЮ ПОБЕДУ (7-9 с двух карт)
            const playerNatural = isNaturalWin(playerScore, cards.player.length);
            const bankerNatural = isNaturalWin(bankerScore, cards.banker.length);
            
            // Если у кого-то натуралка - не показываем добор, ждем завершения
            if (playerNatural || bankerNatural) {
                message = `⏱№${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) - ${cards.bScore} (${formatCards(cards.banker)})`;
            } else {
                // Определяем, кто сейчас добирает (только если нет натуралки)
                const playerHitting = playerScore <= 5 && cards.player.length === 2;
                const bankerHitting = bankerScore <= 5 && cards.banker.length === 2 && cards.player.length >= 2;
                
                if (playerHitting && cards.player.length === 2) {
                    message = `⏱№${gameNumber} 👉${cards.pScore} (${formatCards(cards.player)}) - ${cards.bScore} (${formatCards(cards.banker)})`;
                    console.log(`👆 Игрок добирает карту (${cards.pScore} очков)`);
                } else if (bankerHitting && cards.banker.length === 2) {
                    message = `⏱№${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) -👉${cards.bScore} (${formatCards(cards.banker)})`;
                    console.log(`👆 Банкир добирает карту (${cards.bScore} очков)`);
                } else {
                    message = `⏱№${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) - ${cards.bScore} (${formatCards(cards.banker)})`;
                }
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
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    try {
        await page.goto(URL);
        console.log('🔍 Ищу первый стол с таймером...');

        let liveLink = null;
        while (!liveLink) {
            liveLink = await findFirstLiveGame(page);
            if (!liveLink) {
                await page.waitForTimeout(1000);
            }
        }

        console.log('🎯 Захожу в стол:', liveLink);
        await page.click(`a[href="${liveLink}"]`);
        await page.waitForTimeout(3000);

        // ПОЛУЧАЕМ НОМЕР СТОЛА
        let gameNumber = await page.evaluate(() => {
            const infoEl = document.querySelector('.dashboard-game-info__additional-info');
            if (infoEl && infoEl.textContent.trim()) {
                return infoEl.textContent.trim();
            }
            
            const timeEl = document.querySelector('.dashboard-game-info__time, .dashboard-game-info__period');
            if (timeEl && timeEl.textContent.trim()) {
                const match = timeEl.textContent.trim().match(/\d+$/);
                if (match) return match[0];
            }
            
            return null;
        });

        if (!gameNumber) {
            gameNumber = (parseInt(lastGameNumber) + 1).toString();
            console.log('⚠️ Номер не найден, присваиваю:', gameNumber);
        } else {
            console.log('🎰 Номер стола:', gameNumber);
        }

        lastGameNumber = gameNumber;
        fs.writeFileSync(LAST_NUMBER_FILE, gameNumber);

        let attempts = 0;
        let cards = { player: [], banker: [] };
        while (attempts < 12 && (cards.player.length === 0 || cards.banker.length === 0)) {
            await page.waitForTimeout(5000);
            cards = await getCards(page);
            attempts++;
        }

        if (cards.player.length > 0 && cards.banker.length > 0) {
            const finished = await monitorGame(page, gameNumber);
            if (finished) {
                console.log('🏁 Завершаем сессию');
            }
        }
    } catch (error) {
        console.log('Ошибка:', error.message);
    } finally {
        await browser.close();
        console.log('Браузер закрыт');
        lastMessageId = null;
        lastMessageText = '';
    }
}

// Бесконечный цикл
(async () => {
    console.log('🤖 Бот запущен. Последний номер:', lastGameNumber);
    while (true) {
        await run();
    }
})();
